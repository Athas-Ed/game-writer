from __future__ import annotations

import argparse
import time
import uuid
from typing import Any, Dict, List, Optional


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OpenAI-compatible /v1/chat/completions server (base + LoRA adapter).")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--model_name_or_path", default="Qwen/Qwen2.5-0.5B-Instruct")
    p.add_argument("--adapter_path", required=True, help="Path to LoRA adapter dir (output_dir of qlora_sft).")
    p.add_argument(
        "--load_in_4bit",
        type=int,
        default=0,
        help="Use bitsandbytes 4bit quantization for base model (0/1). Default 0 for compatibility.",
    )
    p.add_argument("--max_new_tokens", type=int, default=512)
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--top_p", type=float, default=0.9)
    return p.parse_args()


def _messages_to_prompt(tokenizer, messages: List[Dict[str, Any]]) -> str:
    """优先使用模型自带 chat_template（与 Instruct 训练一致）。"""
    openai_msgs = []
    for m in messages:
        role = str(m.get("role", "")).strip()
        content = str(m.get("content", "")).strip()
        if not content:
            continue
        if role not in {"system", "user", "assistant"}:
            role = "user"
        openai_msgs.append({"role": role, "content": content})
    if getattr(tokenizer, "chat_template", None) and openai_msgs:
        return str(
            tokenizer.apply_chat_template(
                openai_msgs,
                tokenize=False,
                add_generation_prompt=True,
            )
        )
    parts: List[str] = []
    for m in openai_msgs:
        if m["role"] == "system":
            parts.append(f"[系统]\n{m['content']}")
        elif m["role"] == "assistant":
            parts.append(f"[助手]\n{m['content']}")
        else:
            parts.append(f"[用户]\n{m['content']}")
    parts.append("[助手]\n")
    return "\n\n".join(parts)


def main() -> None:
    args = _parse_args()

    import torch
    from fastapi import FastAPI
    from pydantic import BaseModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    import uvicorn

    use_bf16 = bool(torch.cuda.is_available() and getattr(torch.cuda, "is_bf16_supported", lambda: False)())
    compute_dtype = torch.bfloat16 if use_bf16 else torch.float16

    tokenizer = AutoTokenizer.from_pretrained(args.model_name_or_path, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    if args.load_in_4bit:
        from transformers import BitsAndBytesConfig

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=compute_dtype,
        )
        base = AutoModelForCausalLM.from_pretrained(
            args.model_name_or_path,
            quantization_config=bnb_config,
            device_map="auto",
            dtype="auto",
        )
    else:
        base = AutoModelForCausalLM.from_pretrained(
            args.model_name_or_path,
            device_map="auto",
            dtype=compute_dtype,
        )
    base.config.use_cache = True

    model = PeftModel.from_pretrained(base, args.adapter_path)
    model.eval()

    app = FastAPI()

    class ChatMessage(BaseModel):
        role: str
        content: str

    class ChatCompletionsRequest(BaseModel):
        model: Optional[str] = None
        messages: List[ChatMessage]
        temperature: Optional[float] = None
        top_p: Optional[float] = None
        max_tokens: Optional[int] = None
        stream: Optional[bool] = False

    @app.get("/v1/models")
    def list_models() -> Dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {"id": args.model_name_or_path, "object": "model"},
            ],
        }

    @app.post("/v1/chat/completions")
    def chat_completions(req: ChatCompletionsRequest) -> Dict[str, Any]:
        prompt = _messages_to_prompt(tokenizer, [m.model_dump() for m in req.messages])

        max_new = int(req.max_tokens or args.max_new_tokens)
        temperature = float(req.temperature if req.temperature is not None else args.temperature)
        top_p = float(req.top_p if req.top_p is not None else args.top_p)

        inputs = tokenizer(prompt, return_tensors="pt")
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

        input_len = int(inputs["input_ids"].shape[1])
        gen_kw: Dict[str, Any] = dict(
            max_new_tokens=max_new,
            do_sample=temperature > 0,
            pad_token_id=tokenizer.eos_token_id,
            repetition_penalty=1.12,
            no_repeat_ngram_size=4,
        )
        if temperature > 0:
            gen_kw["temperature"] = max(0.0, temperature)
            gen_kw["top_p"] = top_p
        with torch.inference_mode():
            out_ids = model.generate(**inputs, **gen_kw)

        new_ids = out_ids[0, input_len:]
        content = tokenizer.decode(new_ids, skip_special_tokens=True).strip()

        created = int(time.time())
        cid = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        return {
            "id": cid,
            "object": "chat.completion",
            "created": created,
            "model": req.model or args.model_name_or_path,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
        }

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()


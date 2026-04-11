from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .sft_system_prompt import system_prompt_for_user_message


@dataclass
class Case:
    name: str
    """单轮对话里 user 的完整内容（不含助手回复）。"""
    user_content: str
    """与训练集 instruction+input 对齐；None 则用全局 --max_new_tokens。"""
    max_new_tokens: Optional[int] = None


# user 文案与 training/datasets/style_demo_alpaca.jsonl 中对应样本 instruction+input 保持一致
_MD_INST = (
    "你是“游戏编剧工作台”的写作助手。请把用户输入的需求改写成一段“可直接复制到设定文档”的 Markdown。"
    "要求：1) 使用二级标题，且三个标题必须各单独成行、一字不差为：## 目标、## 约束、## 输出"
    "（禁止写成如「## 目标的设定」「## 输出内容」等变体）。2) 输出用中文。3) 不要提及你是 AI。"
    "4) 禁止使用“### …”作为上述三段标题。5) 不要前言、后记或解释性套话。"
    "6) 只允许这三段及其下内容，禁止 # 一级标题，禁止「开场白」「结尾语」等额外汇总段。"
)
_OUTLINE_INST = (
    "将用户的写作需求整理成“剧情大纲骨架”，要求每一条以“1.”“2.”编号，且每条不超过 20 字（含标点）。"
    "禁止次级小标题、禁止分段说明、禁止空行分段。"
    "每条用短名词短语，写完自查：该行若超过20字必须改短再输出。"
)

CASES: List[Case] = [
    Case(
        name="Markdown三段结构",
        user_content=_MD_INST + "\n\n输入：我要写一个太空歌剧风格的序章，主角是一个叛逃的导航员。",
        max_new_tokens=280,
    ),
    Case(
        name="6行角色卡（固定字段）",
        user_content=(
            "用户要你输出一个“角色设定卡”。请严格输出 6 行，每行格式为“字段：内容”。"
            "字段依次为：姓名、身份、外貌、性格、目标、秘密。"
            "行与行之间不要空行；不要编号；不要表格；不要额外说明。\n\n"
            "输入：角色：林夕，星环联盟的工程师，擅长修复能源系统。"
        ),
        max_new_tokens=220,
    ),
    Case(
        name="编号大纲（每条<=20字）",
        user_content=_OUTLINE_INST + "\n\n输入：写一个发生在废土小镇的悬疑故事，凶手是镇长。",
        max_new_tokens=200,
    ),
]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare base vs base+LoRA adapter on fixed prompts.")
    p.add_argument("--model_name_or_path", default="models/Qwen2.5-0.5B-Instruct")
    p.add_argument("--adapter_path", default="", help="LoRA adapter dir. If empty, only run base.")
    p.add_argument(
        "--load_in_4bit",
        type=int,
        default=0,
        help="Use bitsandbytes 4bit quantization (0/1). Default 0 to avoid CUDA/bnb mismatch.",
    )
    p.add_argument("--max_new_tokens", type=int, default=512)
    p.add_argument("--temperature", type=float, default=0.0, help="0 for greedy decoding (格式更稳).")
    p.add_argument("--top_p", type=float, default=0.9)
    p.add_argument("--repetition_penalty", type=float, default=1.15)
    p.add_argument("--no_repeat_ngram_size", type=int, default=4)
    p.add_argument(
        "--no_system",
        action="store_true",
        help="不传 system 消息（仍会用模型默认 system，仅用于对照实验）",
    )
    return p.parse_args()


def _load_model(model_name_or_path: str, adapter_path: Optional[str], *, load_in_4bit: bool):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    use_bf16 = bool(torch.cuda.is_available() and getattr(torch.cuda, "is_bf16_supported", lambda: False)())
    compute_dtype = torch.bfloat16 if use_bf16 else torch.float16

    tok = AutoTokenizer.from_pretrained(model_name_or_path, local_files_only=True, use_fast=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    if load_in_4bit:
        from transformers import BitsAndBytesConfig

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=compute_dtype,
        )
        base = AutoModelForCausalLM.from_pretrained(
            model_name_or_path,
            local_files_only=True,
            quantization_config=bnb_config,
            device_map="auto",
            dtype="auto",
        )
    else:
        base = AutoModelForCausalLM.from_pretrained(
            model_name_or_path,
            local_files_only=True,
            device_map="auto",
            dtype=compute_dtype,
        )
    base.eval()

    if adapter_path:
        from peft import PeftModel

        model = PeftModel.from_pretrained(base, adapter_path, is_trainable=False)
        model.eval()
        return tok, model

    return tok, base


def _build_prompt_from_messages(
    tok, user_content: str, *, system_text: Optional[str]
) -> Tuple[str, bool]:
    """
    返回 (prompt_string, used_chat_template)。
    若 tokenizer 无 chat_template，则退回简单拼接（与旧行为接近）。
    """
    messages: List[dict] = []
    if system_text:
        messages.append({"role": "system", "content": system_text})
    messages.append({"role": "user", "content": user_content})
    tpl = getattr(tok, "chat_template", None)
    if tpl:
        prompt = tok.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        return str(prompt), True
    sys_prefix = f"[系统]\n{system_text}\n\n" if system_text else ""
    legacy = f"{sys_prefix}### 用户\n{user_content}\n\n### 助手\n"
    return legacy, False


def _generate(
    tok,
    model,
    user_content: str,
    *,
    system_text: Optional[str],
    max_new_tokens: int,
    temperature: float,
    top_p: float,
    repetition_penalty: float,
    no_repeat_ngram_size: int,
) -> str:
    import torch
    from transformers import GenerationConfig

    prompt, _ = _build_prompt_from_messages(tok, user_content, system_text=system_text)
    inputs = tok(prompt, return_tensors="pt")
    input_len = int(inputs["input_ids"].shape[1])
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    do_sample = temperature > 0
    eos_id = tok.eos_token_id
    pad_id = eos_id if eos_id is not None else None

    # 用独立 GenerationConfig，避免与预训练里残留的 temperature/top_p/top_k 合并后触发“无效参数”告警
    if do_sample:
        gen_cfg = GenerationConfig(
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=max(0.0, float(temperature)),
            top_p=float(top_p),
            pad_token_id=pad_id,
            eos_token_id=eos_id,
            repetition_penalty=float(repetition_penalty),
            no_repeat_ngram_size=int(no_repeat_ngram_size),
        )
    else:
        gen_cfg = GenerationConfig(
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=pad_id,
            eos_token_id=eos_id,
            repetition_penalty=float(repetition_penalty),
            no_repeat_ngram_size=int(no_repeat_ngram_size),
        )

    with torch.inference_mode():
        out_ids = model.generate(**inputs, generation_config=gen_cfg)

    new_ids = out_ids[0, input_len:]
    return tok.decode(new_ids, skip_special_tokens=True).strip()


def main() -> None:
    args = _parse_args()

    use_system = not args.no_system

    tok_base, model_base = _load_model(args.model_name_or_path, adapter_path=None, load_in_4bit=bool(args.load_in_4bit))
    tok_adapt = None
    model_adapt = None
    if args.adapter_path:
        tok_adapt, model_adapt = _load_model(
            args.model_name_or_path, adapter_path=args.adapter_path, load_in_4bit=bool(args.load_in_4bit)
        )

    st0 = system_prompt_for_user_message(CASES[0].user_content) if use_system else None
    _, used_tpl = _build_prompt_from_messages(tok_base, CASES[0].user_content, system_text=st0)
    st0_preview = (st0[:24] + "…") if st0 and len(st0) > 24 else (st0 or "")
    print(
        f"[Info] prompt_mode={'chat_template' if used_tpl else 'legacy_concat'}; "
        f"system={'per-task' if use_system else 'off'} (case1_preview={st0_preview!r})"
    )

    for c in CASES:
        system_text = system_prompt_for_user_message(c.user_content) if use_system else None
        prompt_show, _ = _build_prompt_from_messages(tok_base, c.user_content, system_text=system_text)
        print("\n" + "=" * 88)
        print(f"[Case] {c.name}")
        print("-" * 88)
        print("[User content]")
        print(c.user_content)
        print("-" * 88)
        print("[Rendered prompt head]")
        head = prompt_show[:1200] + ("…" if len(prompt_show) > 1200 else "")
        print(head)
        print("-" * 88)
        mnt = c.max_new_tokens if c.max_new_tokens is not None else args.max_new_tokens
        print("[Base Output]")
        print(
            _generate(
                tok_base,
                model_base,
                c.user_content,
                system_text=system_text,
                max_new_tokens=mnt,
                temperature=args.temperature,
                top_p=args.top_p,
                repetition_penalty=args.repetition_penalty,
                no_repeat_ngram_size=args.no_repeat_ngram_size,
            )
        )
        if model_adapt is not None and tok_adapt is not None:
            print("-" * 88)
            print("[Adapter Output]")
            print(
                _generate(
                    tok_adapt,
                    model_adapt,
                    c.user_content,
                    system_text=system_text,
                    max_new_tokens=mnt,
                    temperature=args.temperature,
                    top_p=args.top_p,
                    repetition_penalty=args.repetition_penalty,
                    no_repeat_ngram_size=args.no_repeat_ngram_size,
                )
            )


if __name__ == "__main__":
    main()

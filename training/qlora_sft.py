from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .sft_system_prompt import system_prompt_for_instruction


@dataclass
class Args:
    model_name_or_path: str
    dataset_name: str
    dataset_split: str
    dataset_path: str
    output_dir: str
    max_seq_length: int
    per_device_train_batch_size: int
    gradient_accumulation_steps: int
    learning_rate: float
    num_train_epochs: float
    logging_steps: int
    save_steps: int
    seed: int
    warmup_ratio: float
    lr_scheduler_type: str
    load_in_4bit: int


def _parse_args() -> Args:
    p = argparse.ArgumentParser(description="LoRA/QLoRA SFT demo (Transformers + TRL).")
    p.add_argument("--model_name_or_path", default="Qwen/Qwen2.5-0.5B-Instruct")
    p.add_argument("--dataset_name", default="tatsu-lab/alpaca", help="HF dataset name (used when dataset_path is empty).")
    p.add_argument("--dataset_split", default="train")
    p.add_argument("--dataset_path", default="", help="Local json/jsonl path (alpaca-style: instruction/input/output).")
    p.add_argument("--output_dir", default="training_outputs/qlora_sft")
    p.add_argument("--max_seq_length", type=int, default=1024)
    p.add_argument("--per_device_train_batch_size", type=int, default=1)
    p.add_argument("--gradient_accumulation_steps", type=int, default=16)
    p.add_argument("--learning_rate", type=float, default=2e-4)
    p.add_argument("--num_train_epochs", type=float, default=1.0)
    p.add_argument("--logging_steps", type=int, default=10)
    p.add_argument("--save_steps", type=int, default=200)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--warmup_ratio", type=float, default=0.03)
    p.add_argument("--lr_scheduler_type", default="cosine")
    p.add_argument(
        "--load_in_4bit",
        type=int,
        default=0,
        help="Use QLoRA 4bit quantization via bitsandbytes (0/1). Default 0 for compatibility.",
    )
    ns = p.parse_args()
    return Args(**vars(ns))


def _alpaca_to_user_assistant(ex: Dict[str, Any]) -> tuple[str, str]:
    inst = (ex.get("instruction") or "").strip()
    inp = (ex.get("input") or "").strip()
    out = (ex.get("output") or "").strip()
    if inp:
        user = f"{inst}\n\n输入：{inp}"
    else:
        user = inst
    return user, out


def _alpaca_to_chat_text(tokenizer: Any, ex: Dict[str, Any]) -> str:
    user, assistant = _alpaca_to_user_assistant(ex)
    inst = (ex.get("instruction") or "").strip()
    sys_p = system_prompt_for_instruction(inst)
    if getattr(tokenizer, "chat_template", None):
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
        return str(tokenizer.apply_chat_template(messages, tokenize=False))
    return f"[系统]\n{sys_p}\n\n### 用户\n{user}\n\n### 助手\n{assistant}"


def main() -> None:
    args = _parse_args()

    # 让训练日志更可读
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    import torch
    from datasets import load_dataset  # type: ignore
    from peft import LoraConfig  # type: ignore
    from transformers import (  # type: ignore
        AutoModelForCausalLM,
        AutoTokenizer,
        TrainingArguments,
        set_seed,
    )
    from trl import SFTTrainer  # type: ignore
    import inspect

    set_seed(args.seed)

    if args.dataset_path:
        ds = load_dataset("json", data_files=args.dataset_path, split="train")
    else:
        ds = load_dataset(args.dataset_name, split=args.dataset_split)

    # 训练计算 dtype：优先 bf16（更稳），不支持则退回 fp16
    use_bf16 = bool(torch.cuda.is_available() and getattr(torch.cuda, "is_bf16_supported", lambda: False)())
    compute_dtype = torch.bfloat16 if use_bf16 else torch.float16

    tokenizer = AutoTokenizer.from_pretrained(args.model_name_or_path, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # 与 Qwen Instruct 推理对齐：优先用 tokenizer.chat_template 拼整段监督文本
    ds = ds.map(
        lambda ex: {"text": _alpaca_to_chat_text(tokenizer, ex)},
        remove_columns=ds.column_names,
    )

    if args.load_in_4bit:
        # QLoRA: 需要 bitsandbytes。注意：若你的 PyTorch CUDA 版本过新（如 13.0），
        # bnb 可能没有对应的预编译库，需要切换到 CUDA 12.x 的 torch 或编译 bnb。
        from transformers import BitsAndBytesConfig

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=compute_dtype,
        )
        model = AutoModelForCausalLM.from_pretrained(
            args.model_name_or_path,
            quantization_config=bnb_config,
            device_map="auto",
            dtype="auto",
        )
    else:
        # LoRA（非量化）：不依赖 bitsandbytes，适合当前 CUDA 13.0 环境先跑通流程与效果对比。
        model = AutoModelForCausalLM.from_pretrained(
            args.model_name_or_path,
            device_map="auto",
            dtype=compute_dtype,
        )
    model.config.use_cache = False

    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=None,  # 让 PEFT 自动推断；若不生效可改成显式列表（不同模型命名不同）
    )

    targs = TrainingArguments(
        output_dir=args.output_dir,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        num_train_epochs=args.num_train_epochs,
        logging_steps=args.logging_steps,
        save_steps=args.save_steps,
        warmup_ratio=args.warmup_ratio,
        lr_scheduler_type=args.lr_scheduler_type,
        fp16=not use_bf16,
        bf16=use_bf16,
        report_to=[],
        save_total_limit=2,
        remove_unused_columns=False,
    )

    # TRL 的 SFTTrainer 在不同版本中参数名有变化（不同版本对下面这些字段的支持不一致）：
    # - tokenizer=... / processing_class=...
    # - dataset_text_field / formatting_func
    # - max_seq_length / packing / dataset_kwargs
    #
    # 这里按 __init__ 签名动态裁剪参数，尽量“一份脚本跑多个版本”。
    trainer_kwargs: Dict[str, Any] = dict(
        model=model,
        args=targs,
        train_dataset=ds,
        peft_config=peft_config,
    )
    sig = inspect.signature(SFTTrainer.__init__)
    params = sig.parameters

    # tokenizer / processing_class
    if "processing_class" in params:
        trainer_kwargs["processing_class"] = tokenizer
    elif "tokenizer" in params:
        trainer_kwargs["tokenizer"] = tokenizer

    # text field vs formatting func
    if "dataset_text_field" in params:
        trainer_kwargs["dataset_text_field"] = "text"
    elif "formatting_func" in params:
        # ds 已被 map 成 {"text": "..."}；这里直接取 text 作为格式化结果
        trainer_kwargs["formatting_func"] = lambda ex: ex["text"]

    # seq len / packing
    if "max_seq_length" in params:
        trainer_kwargs["max_seq_length"] = args.max_seq_length
    # 对话格式样本不宜跨条 packing，避免截断在 assistant 中间
    if "packing" in params:
        trainer_kwargs["packing"] = False
    elif "dataset_kwargs" in params:
        trainer_kwargs["dataset_kwargs"] = {
            "packing": False,
            "max_length": args.max_seq_length,
        }

    # 最终再做一次安全裁剪（避免未来版本再改名导致 unexpected keyword）
    trainer_kwargs = {k: v for k, v in trainer_kwargs.items() if k in params}
    trainer = SFTTrainer(**trainer_kwargs)

    trainer.train()
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)


if __name__ == "__main__":
    main()


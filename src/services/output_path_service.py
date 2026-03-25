from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


@dataclass
class OutputTargetsCache:
    mapping: Dict[str, str]
    mtime: Optional[float]


DEFAULT_OUTPUT_TARGETS: Dict[str, str] = {"角色设定": "data/角色设定", "背景设定": "data/背景设定"}


def load_output_targets(output_targets_path: Path, cache: Optional[OutputTargetsCache] = None) -> OutputTargetsCache:
    """
    加载输出目标映射（自动缓存，文件变更自动刷新）。
    """
    if not output_targets_path.exists():
        return OutputTargetsCache(mapping=dict(DEFAULT_OUTPUT_TARGETS), mtime=None)

    try:
        mtime = output_targets_path.stat().st_mtime
    except Exception:
        return cache or OutputTargetsCache(mapping=dict(DEFAULT_OUTPUT_TARGETS), mtime=None)

    if cache is not None and cache.mtime == mtime:
        return cache

    try:
        data = json.loads(output_targets_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("output_targets.json 必须是 JSON 对象")
        mapping: Dict[str, str] = {}
        for k, v in data.items():
            if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                mapping[k.strip()] = v.strip()
        if not mapping:
            mapping = dict(DEFAULT_OUTPUT_TARGETS)
        return OutputTargetsCache(mapping=mapping, mtime=mtime)
    except Exception:
        return OutputTargetsCache(mapping=dict(DEFAULT_OUTPUT_TARGETS), mtime=mtime)


def normalize_write_path(file_path: str, cache: OutputTargetsCache) -> str:
    """
    - 统一使用正斜杠
    - 禁止绝对路径与 .. 路径穿越
    - 使用 output_targets.json 做“口语目录”映射
    """
    p = (file_path or "").strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]

    if p.startswith("/") or re.match(r"^[A-Za-z]:", p):
        raise ValueError("不允许写入绝对路径。请使用相对路径（例如 data/角色设定/xxx.md）。")
    if ".." in p.split("/"):
        raise ValueError("不允许使用 '..' 路径穿越。")

    head = p.split("/", 1)[0] if p else ""
    if head and head in cache.mapping:
        base = cache.mapping[head].strip().replace("\\", "/").rstrip("/")
        tail = p[len(head) :].lstrip("/")
        p = f"{base}/{tail}" if tail else base
    return p


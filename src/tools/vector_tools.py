from __future__ import annotations

import re
from typing import Tuple

from src.tools.vector_retriever import build_index, ensure_index, retrieve_context


def _parse_payload(payload: str, *, default_top_k: int = 6) -> Tuple[str, int]:
    text = (payload or "").strip()
    if not text:
        return "", default_top_k

    # 允许两种常见用法：
    # 1) 纯 query：林夕 年龄
    # 2) kv：query=林夕|top_k=8 或 query=... \n top_k=...
    parts = [p.strip() for p in re.split(r"[|\n]+", text) if p.strip()]
    if not parts:
        return "", default_top_k

    kv: dict[str, str] = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            kv[k.strip().lower()] = v.strip()

    query = (kv.get("query") or kv.get("q") or "").strip()
    top_k_raw = (kv.get("top_k") or kv.get("topk") or "").strip()

    if not query:
        # 没有明确 query=... 则把原始 text 当 query
        query = text

    try:
        top_k = int(top_k_raw) if top_k_raw else default_top_k
    except ValueError:
        top_k = default_top_k

    top_k = max(1, min(20, top_k))
    return query, top_k


def vector_search(payload: str) -> str:
    """
    向量检索：根据关键词或自然语言查询，返回最相关的数据分块（含 chunk_ref）。

    输入：
    - 纯 query：自然语言/关键词
    - 或 kv：`query=...|top_k=8`
    """

    query, top_k = _parse_payload(payload)
    if not query:
        return "VectorSearch：query 为空。"
    return retrieve_context(query, top_k=top_k)


def build_vector_index(payload: str) -> str:
    """
    构建/重建向量索引（持久化到 .vector_index/）。

    输入（可选）：
    - "force=true" 或 "force=1"：强制重建
    - 也可直接给 "force" 作为简写
    """

    text = (payload or "").strip().lower()
    force = False
    if text in {"force", "rebuild"}:
        force = True
    elif "force" in text and ("=1" in text or "=true" in text or "=yes" in text):
        force = True

    col = build_index(force_rebuild=force) if force else ensure_index()
    try:
        n = col.count()
    except Exception:
        n = "未知"
    return f"向量索引就绪：collection={getattr(col, 'name', 'unknown')} | count={n} | force_rebuild={force}"
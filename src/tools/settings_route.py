"""
结构化路由：先列出 data/ 索引、按目录列文件、按路径输出分块+元数据，或转交关键词检索。
输入为单行或多行文本，便于 Agent JSON 内传递。
"""

from __future__ import annotations

import re
from typing import Dict

from src.tools.data_chunks import format_chunks_for_file, format_routing_index, list_files_in_data_subdir
from src.tools.search_docs import search_docs


def _usage() -> str:
    return (
        "SettingsRoute：用法（每次调用选一种子命令，整段作为 input）：\n"
        "1) list — 输出按目录分组的全部 .md 路由索引（大库可能截断文件列表）。\n"
        "2) files dir=角色设定 — 列出 data/角色设定/ 下所有 .md（递归）。\n"
        "3) chunks path=data/角色设定/某某.md — 输出该文件的分块与元数据（chunk_ref、heading 等）。\n"
        "4) search 关键词… — 等价 SearchDocs，跨文件返回 top 证据片段。\n"
        "\n"
        "也可写多行，例如：\n"
        "files\n"
        "dir=背景设定/种族\n"
    )


def _parse_kv_lines(payload: str) -> Dict[str, str]:
    """解析 key=value 行；key 统一小写。"""
    out: Dict[str, str] = {}
    for raw_line in (payload or "").replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip().lower()
            v = v.strip()
            if k:
                out[k] = v
    return out


def settings_route(payload: str) -> str:
    text = (payload or "").strip()
    if not text:
        return _usage()

    lower = text.lower()
    if lower in {"help", "?", "用法"}:
        return _usage()

    # 多行 key=value：files + dir=
    kv = _parse_kv_lines(text)
    if "search" in kv and len(kv) == 1:
        return search_docs(kv["search"])

    # 子命令：list
    first_token = text.split(None, 1)[0].lower()
    if first_token == "list" and len(text.split()) == 1:
        return format_routing_index()

    # files dir=...
    if first_token == "files":
        rest = text[len(text.split(None, 1)[0]) :].strip()
        sub = _parse_kv_lines(rest) if rest else {}
        d = sub.get("dir") or sub.get("path") or rest.replace("dir=", "").replace("path=", "").strip()
        if not d:
            return "SettingsRoute：files 需要 dir=…，例如 files dir=角色设定"
        return list_files_in_data_subdir(d)

    # chunks path=...
    if first_token == "chunks":
        rest = text[len(text.split(None, 1)[0]) :].strip()
        sub = _parse_kv_lines(rest) if rest else {}
        p = sub.get("path") or sub.get("file") or ""
        if not p and rest.startswith("path="):
            p = rest.split("=", 1)[1].strip()
        if not p:
            # chunks data/... 无 path= 前缀
            p = rest.strip()
        if not p:
            return "SettingsRoute：chunks 需要 path=data/…，例如 chunks path=data/角色设定/林夕.md"
        return format_chunks_for_file(p)

    # search …
    if first_token == "search":
        q = text[len(text.split(None, 1)[0]) :].strip()
        if not q:
            return "SettingsRoute：search 需要关键词，例如 search 艾莉丝 年龄"
        return search_docs(q)

    # 单行简写 path=data/... 视为 chunks
    m = re.match(r"^path\s*=\s*(.+)$", text, re.IGNORECASE)
    if m:
        return format_chunks_for_file(m.group(1).strip())

    # 仅 key=value 单行
    if "=" in text and "\n" not in text:
        k, v = text.split("=", 1)
        kl = k.strip().lower()
        v = v.strip()
        if kl == "dir" and v:
            return list_files_in_data_subdir(v)
        if kl in {"path", "file"} and v.lower().endswith(".md"):
            return format_chunks_for_file(v)

    return (
        "SettingsRoute：无法解析输入。请使用 list / files dir=… / chunks path=… / search 关键词。\n"
        + _usage()
    )

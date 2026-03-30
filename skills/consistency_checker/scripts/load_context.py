"""
为设定一致性检查组装上下文：可选 focus 关键词检索 + 目录范围 + 广泛节选。
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence, Tuple

from src.tools.file_tools import read_settings_bundle
from src.tools.search_docs import gather_evidence_context


def parse_options_and_hint(user_request: str) -> Tuple[dict, str]:
    """
    从用户输入中解析可选行，其余作为「检查侧重点」自然语言提示。
    支持行首：
    - focus= 或 focus：关键词1,关键词2
    - dirs= / scope= / 范围= 角色设定 或 角色设定,背景设定
    """
    opts: dict = {"focus": [], "dirs": None}
    hint_lines: List[str] = []
    for line in (user_request or "").splitlines():
        s = line.strip()
        if not s:
            hint_lines.append(line)
            continue
        m_focus = re.match(r"^focus\s*[=:：]\s*(.+)$", s, re.IGNORECASE)
        if m_focus:
            raw = m_focus.group(1)
            opts["focus"] = [x.strip() for x in re.split(r"[,，;；]", raw) if x.strip()]
            continue
        m_dirs = re.match(r"^(?:dirs?|scope|范围)\s*[=:：]\s*(.+)$", s, re.IGNORECASE)
        if m_dirs:
            raw = m_dirs.group(1).strip()
            opts["dirs"] = [x.strip() for x in re.split(r"[,，;；]", raw) if x.strip()]
            continue
        hint_lines.append(line)
    hint = "\n".join(hint_lines).strip()
    return opts, hint


def _dirs_tuple(dirs: Optional[Sequence[str]]) -> Tuple[str, ...]:
    if not dirs:
        return ("角色设定", "背景设定")
    return tuple(str(d) for d in dirs if d)


def build_check_context(user_request: str) -> Tuple[str, str]:
    """
    返回 (送入 LLM 的设定正文, 给用户的简短说明)。
    """
    opts, _hint = parse_options_and_hint(user_request)
    focus_list: List[str] = opts.get("focus") or []
    dir_list: Optional[List[str]] = opts.get("dirs")

    settings_dirs = _dirs_tuple(dir_list)
    notes: List[str] = []

    if focus_list:
        chunks: List[str] = []
        for kw in focus_list[:6]:
            ev = gather_evidence_context(kw.strip(), top_k=10, max_total_chars=12_000)
            if ev:
                chunks.append(f"## 与「{kw}」检索相关的分块\n\n{ev}")
        if chunks:
            notes.append(f"已按 focus 检索：{', '.join(focus_list[:6])}")
        appendix = read_settings_bundle(
            settings_dirs=settings_dirs,
            max_files_per_dir=120,
            max_total_chars=32_000,
        )
        body = "\n\n---\n\n".join(chunks) if chunks else ""
        if body:
            context = body + "\n\n---\n\n## 设定库广泛节选（兜底）\n\n" + appendix
        else:
            context = (
                "（focus 关键词未命中任何分块，已改为仅按目录广泛读取。）\n\n"
                + read_settings_bundle(
                    settings_dirs=settings_dirs,
                    max_files_per_dir=150,
                    max_total_chars=95_000,
                )
            )
            notes.append("focus 无命中，已用广泛读取")
        return context, "; ".join(notes) if notes else "按 focus + 目录节选"

    bundle = read_settings_bundle(
        settings_dirs=settings_dirs,
        max_files_per_dir=180,
        max_total_chars=100_000,
    )
    scope_note = "、".join(settings_dirs) if settings_dirs else "默认目录"
    return bundle, f"已读取 data 下：{scope_note}（广泛模式）"

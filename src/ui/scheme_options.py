"""
从助手 Markdown 中解析「方案1 / 方案2 …」结构，供对话界面渲染选择按钮。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

__all__ = ["extract_scheme_options", "message_scheme_options", "assistant_message_dict"]


def extract_scheme_options(text: str) -> Optional[List[Dict[str, str]]]:
    """
    至少识别到 2 个「方案N：」标题才返回列表，与 outline-writer 输出格式对齐。
    """
    if not text or "方案" not in text:
        return None
    pat = re.compile(r"(?:^|\n)\s*方案\s*(\d+)\s*[:：]\s*", re.MULTILINE)
    matches = list(pat.finditer(text))
    if len(matches) < 2:
        return None
    options: List[Dict[str, str]] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        preview = body.split("\n", 1)[0].strip()
        if len(preview) > 48:
            preview = preview[:45] + "…"
        num = m.group(1)
        options.append(
            {
                "id": num,
                "label": f"方案{num}",
                "preview": preview or f"查看方案{num}",
            }
        )
    return options


def message_scheme_options(msg: Dict[str, Any]) -> Optional[List[Dict[str, str]]]:
    cached = msg.get("scheme_options")
    if isinstance(cached, list) and cached:
        return cached
    if msg.get("role") != "assistant":
        return None
    return extract_scheme_options(str(msg.get("content") or ""))


def assistant_message_dict(content: str) -> Dict[str, Any]:
    msg: Dict[str, Any] = {"role": "assistant", "content": content}
    opts = extract_scheme_options(content)
    if opts:
        msg["scheme_options"] = opts
    return msg

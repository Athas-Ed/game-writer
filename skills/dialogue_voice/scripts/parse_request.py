"""解析对白技能的可选行：出场角色、语气、格式等。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class DialogueRequest:
    speakers: List[str]
    tone_hints: List[str]
    format_hint: Optional[str]
    scene: str


def parse_dialogue_request(text: str) -> DialogueRequest:
    speakers: List[str] = []
    tone_hints: List[str] = []
    format_hint: Optional[str] = None
    body_lines: List[str] = []

    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            body_lines.append(line)
            continue

        m = re.match(r"^(?:speakers?|角色|出场)\s*[=:：]\s*(.+)$", s, re.IGNORECASE)
        if m:
            speakers = [x.strip() for x in re.split(r"[,，;；]", m.group(1)) if x.strip()]
            continue

        m2 = re.match(r"^(?:tone|语气|口吻)\s*[=:：]\s*(.+)$", s, re.IGNORECASE)
        if m2:
            tone_hints.append(m2.group(1).strip())
            continue

        m3 = re.match(r"^(?:format|格式)\s*[=:：]\s*(.+)$", s, re.IGNORECASE)
        if m3:
            format_hint = m3.group(1).strip()
            continue

        body_lines.append(line)

    scene = "\n".join(body_lines).strip()
    return DialogueRequest(
        speakers=speakers,
        tone_hints=tone_hints,
        format_hint=format_hint,
        scene=scene,
    )


def retrieval_seed(req: DialogueRequest) -> str:
    parts: List[str] = []
    if req.speakers:
        parts.append(" ".join(req.speakers))
    if req.scene:
        parts.append(req.scene[:500])
    return " ".join(parts).strip() or (req.scene or "")

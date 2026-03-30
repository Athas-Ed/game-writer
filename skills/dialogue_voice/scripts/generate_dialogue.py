"""调用 LLM 生成两组对白方案（方案1 / 方案2，便于界面点选）。"""

from __future__ import annotations

import re
from typing import List

from src.tools.llm_tools import llm_generate

from parse_request import DialogueRequest


def _split_scheme_blocks(text: str) -> List[str]:
    """按「方案N：」切分正文，返回各方案块（不含标题行）。"""
    if not text:
        return []
    pat = re.compile(r"(?:^|\n)\s*方案\s*(\d+)\s*[:：]\s*", re.MULTILINE)
    matches = list(pat.finditer(text))
    if len(matches) < 1:
        return []
    blocks: List[str] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        blocks.append(text[start:end].strip())
    return blocks


def generate_dialogue_two_variants(req: DialogueRequest, context: str) -> tuple[str, List[str]]:
    """
    返回 (原始 LLM 全文, 解析出的方案块列表)。
    若模型未按格式输出，blocks 可能少于 2，由 run.py 兜底。
    """
    spk = "、".join(req.speakers) if req.speakers else "（未指定，请根据场景自拟说话人）"
    tones = "；".join(req.tone_hints) if req.tone_hints else "（未指定：可各方案尝试不同语气）"
    fmt = req.format_hint or "人物名：台词，一行一句；需要时可加简短旁白或系统提示，用【旁白】标注。"

    prompt = f"""你是游戏编剧，擅长写可落地的角色对白与语气。

以下是项目设定（角色、世界观等），必须遵守其中已写明的事实，不要编造与设定冲突的信息：
---
{context}
---

【场景与需求】
{req.scene}

【出场角色】{spk}
【语气/口吻偏好】{tones}
【格式要求】{fmt}

请输出 **恰好两组** 对白方案，便于制作人挑选。每组采用不同语气或节奏（例如：一组更克制、一组更外放；或一组偏喜剧、一组偏严肃），但都要符合设定。

**必须**使用以下标题格式（方案后加中文冒号）：
方案1：
（先一行简要说明本版语气/侧重点）
然后写对白正文。

方案2：
（同上）
然后写对白正文。

不要输出方案3。不要在最前面加开场白或总结；直接从「方案1：」开始。
"""
    raw = llm_generate(prompt, temperature=0.75)
    blocks = _split_scheme_blocks(raw)
    return raw, blocks

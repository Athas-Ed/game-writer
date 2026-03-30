# skills/outline_writer/scripts/generate_outlines.py
import re

from src.tools.llm_tools import llm_generate

# 主格式：【方案N】 分段；不用 re.M，避免 $ 在每行末尾截断正文
_OUTLINE_BLOCK_RE = re.compile(r"【方案([1-5])】\s*([\s\S]*?)(?=【方案[1-5]】|\Z)")

# 回退：行首「数字 + .、． + 空格」且该行总长度足够，减少把短条目当成新大纲的概率
_FALLBACK_ITEM_RE = re.compile(
    r"^\s*([1-5])\s*[\.、．]\s+(.{40,})$",
    re.MULTILINE,
)


def _parse_outlines_bracketed(response: str) -> list[str]:
    """按 【方案1】…【方案N】 抽取正文；自动忽略此前的前言/分析。"""
    text = response.strip()
    if not text:
        return []
    blocks: list[tuple[int, str]] = []
    for m in _OUTLINE_BLOCK_RE.finditer(text):
        idx = int(m.group(1))
        body = m.group(2).strip()
        if body:
            blocks.append((idx, body))
    blocks.sort(key=lambda x: x[0])
    return [b[1] for b in blocks]


def _parse_outlines_fallback(response: str, num_options: int) -> list[str]:
    """
    旧版「1. 2. 3.」列表式输出。仅在行首且后续文字足够长时切分，降低与分点亮点混淆的概率。
    """
    text = response.strip()
    if not text:
        return []

    starts: list[tuple[int, int]] = []
    for m in _FALLBACK_ITEM_RE.finditer(text):
        pos = m.start()
        n = int(m.group(1))
        if 1 <= n <= num_options:
            starts.append((pos, n))
    if not starts:
        return []

    starts.sort(key=lambda x: x[0])
    outlines: list[str] = []
    for i, (pos, _n) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        chunk = text[pos:end].strip()
        if chunk:
            outlines.append(chunk)
    return outlines


def generate_outlines(one_line: str, context: str, num_options: int = 3) -> list:
    prompt = f"""你是一个游戏编剧助手。以下是当前项目的角色、背景设定：
{context}

现在用户提供了一句话剧情描述：“{one_line}”
请根据设定，创作恰好 {num_options} 个不同风格的剧情大纲方案。每个方案用几段文字描述核心情节、冲突和悬念（每方案约 200～400 字）。

【格式要求 — 必须严格遵守，否则无法解析】
1. 不要写任何前言、结语、客套话。
2. 不要写「分析与建议」「亮点」「潜在问题」等与大纲方案无关的段落。
3. 不要用「1.」「2.」列举亮点或评价；只允许用下方 【方案N】 作为分段标记。
4. 按顺序输出 {num_options} 个方案，每个方案必须以单独一行开头，格式 exactly：

【方案1】
（第一段正文，可多行）

【方案2】
（正文）

【方案3】
（正文）

（若 num_options 不为 3，则依次写到 【方案{num_options}】。）
"""
    response = llm_generate(prompt, temperature=0.65)

    outlines = _parse_outlines_bracketed(response)
    if not outlines:
        outlines = _parse_outlines_fallback(response, num_options)
    if not outlines and response.strip():
        return [response.strip()]
    return outlines[:num_options]

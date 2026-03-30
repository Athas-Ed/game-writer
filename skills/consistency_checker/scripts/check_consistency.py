"""调用 LLM 对设定正文做矛盾与疑点审计。"""

from __future__ import annotations

from src.tools.llm_tools import llm_generate

_MAX_CORPUS_CHARS = 105_000


def run_consistency_check(setting_corpus: str, user_hint: str = "") -> str:
    corpus = (setting_corpus or "").strip()
    if not corpus:
        return "设定正文为空：请确认 data/ 下存在可读 Markdown，或调整 dirs=/focus= 范围。"

    truncated_note = ""
    if len(corpus) > _MAX_CORPUS_CHARS:
        corpus = corpus[:_MAX_CORPUS_CHARS]
        truncated_note = (
            f"\n【系统说明】设定正文已在 {_MAX_CORPUS_CHARS} 字符处截断，审计可能遗漏截断以外的内容。\n"
        )

    hint_block = ""
    if (user_hint or "").strip():
        hint_block = f"\n用户补充侧重点（优先关注）：\n{user_hint.strip()}\n"

    prompt = f"""你是游戏叙事设定审计员。请在下列 Markdown 设定库中查找**明确或高度可疑的矛盾**，包括但不限于：
- 同一角色、地点、组织、道具在不同段落中的事实冲突（年龄、生死、职务、亲属关系、能力边界等）
- 时间线无法自洽（事件顺序、年份、时代背景）
- 地理、势力范围、国家/城邦设定前后不一致
- 同一实体多种称谓、译名、编号混用且可能指代冲突

设定库正文：
---
{corpus}
---{truncated_note}{hint_block}

输出要求（使用 Markdown）：
1. 首行写摘要：「共发现 N 条待核实问题」或「未发现明显矛盾」。
2. 若有疑点：用有序列表，每条包含小标题行 **类型**（角色/时间线/地理/称谓/其他），并分点写：
   - **矛盾简述**
   - **涉及依据**（尽量写出文件路径或小标题；无法定位则写「某处提到」并引用原文短语）
   - **建议**（如何核实或修改）
3. 不得编造正文中不存在的设定；证据不足时标为「弱疑点」。
4. 若上文含截断说明，请在结尾再提醒一次可能遗漏。
"""
    return llm_generate(prompt, temperature=0.25)

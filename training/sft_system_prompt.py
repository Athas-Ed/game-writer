"""
按任务拆分的 system：避免把 Markdown/角色卡/大纲规则混在一条里，减轻小模型交叉干扰。
"""

from __future__ import annotations

SFT_SYSTEM_GENERIC = (
    "你是中文写作助手。只输出用户要求的正文，不要前言、后记、道歉或套话；不要解释你在做什么。"
)

SFT_SYSTEM_MARKDOWN = (
    "你是中文写作助手。只输出用户要的 Markdown 正文。\n"
    "硬性格式：正文里必须有且仅有三个二级标题行，且必须一字不差写成单独一行：## 目标、## 约束、## 输出（"
    "不要在「目标/约束/输出」后再加任何字，例如禁止「## 目标的设定」）。\n"
    "每段标题下用列表或短句；禁止 # 一级标题；禁止额外章节如「开场白」「结尾语」；禁止用 1.2.3. 包裹整篇。"
)

SFT_SYSTEM_CHARACTER = (
    "你是中文写作助手。只输出角色设定卡正文。\n"
    "硬性格式：恰好 6 行，依次以「姓名：」「身份：」「外貌：」「性格：」「目标：」「秘密：」开头，"
    "冒号后接内容；行首禁止写 1. 2.；禁止空行；禁止表格。"
)

SFT_SYSTEM_OUTLINE = (
    "你是中文写作助手。只输出剧情大纲骨架。\n"
    "硬性格式：每行一条，行首为 1. 2. 3. …；每行尽量短（名词短语），全行汉字+标点合计不超过 20；"
    "写完后心里数一遍，超长就改短再输出。\n"
    "禁止：「背景设定」等次级标题；禁止缩进子列表；禁止分号连接两个长句占一行。"
)


def system_prompt_for_instruction(instruction: str) -> str:
    """根据 Alpaca 的 instruction 字段选用 system。"""
    s = instruction or ""
    if "角色设定卡" in s:
        return SFT_SYSTEM_CHARACTER
    if "剧情大纲骨架" in s:
        return SFT_SYSTEM_OUTLINE
    if "Markdown" in s or "可直接复制到设定文档" in s:
        return SFT_SYSTEM_MARKDOWN
    return SFT_SYSTEM_GENERIC


def system_prompt_for_user_message(user_content: str) -> str:
    """对比脚本里 user 块 = instruction + \\n\\n输入：…，用 instruction 段做路由。"""
    before = user_content.split("\n\n输入：", 1)[0]
    return system_prompt_for_instruction(before)


SFT_SYSTEM_PROMPT = SFT_SYSTEM_GENERIC

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class AgentRuntimeFlags:
    log_level: str  # NONE / INFO / DEBUG
    prefs_enabled: bool  # whether preference proposal + write is enabled

    @property
    def is_info(self) -> bool:
        return self.log_level in {"INFO", "DEBUG"}

    @property
    def is_debug(self) -> bool:
        return self.log_level == "DEBUG"


def get_runtime_flags() -> AgentRuntimeFlags:
    log_level = os.getenv("AGENT_LOG_LEVEL", "INFO").strip().upper()
    if os.getenv("AGENT_VERBOSE", "1") == "0":
        log_level = "NONE"
    if log_level not in {"NONE", "INFO", "DEBUG"}:
        log_level = "INFO"

    prefs_enabled = os.getenv("PREFERENCES_WRITE_ENABLED", "1").strip() != "0"
    return AgentRuntimeFlags(log_level=log_level, prefs_enabled=prefs_enabled)


def should_short_circuit_for_preferences(user_input: str, prefs_enabled: bool) -> bool:
    """偏好功能关闭时：用户输入像“改良意见”则短路，避免后台跑工具浪费。"""
    if prefs_enabled:
        return False
    return bool(re.search(r"(偏好|约束|规则|习惯|以后|改良|优化|记住|下次|请你记)", user_input or ""))


def build_json_only_prompt(
    *,
    tool_descriptions: str,
    skill_descriptions: str,
    history_text: str,
    preferences_text: str,
    history_turns: int,
    user_input: str,
    prefs_enabled: bool,
) -> str:
    prefs_flow_rule = (
        "- 当用户提出“希望以后都这样/优化/习惯/偏好/约束/规则”等改良意见时：\n"
        "  1) 先用 ProposePreference 把改良意见归纳成 1 条可执行规则；\n"
        "  2) 用 final.output 向用户展示该规则，并明确询问是否“确认写入偏好”（不要直接写入）；\n"
        "  3) 只有当用户明确回复“确认/同意写入/保存偏好/确认保存”等肯定语时，才调用 UpdatePreferences 写入并查重。"
        if prefs_enabled
        else "- 当前已关闭“偏好建议/写入”功能：不要提出偏好建议，也不要调用 ProposePreference / UpdatePreferences。"
    )

    return f"""你是一个游戏编剧助手，你只能按“严格 JSON-only”协议输出结果，禁止输出任何非 JSON 内容。

可用工具：
{tool_descriptions}

当前可用技能（通过 RunSkill 调用）：
{skill_descriptions}

历史对话（最近{history_turns}轮，供你保持连续讨论）：
{history_text}

项目偏好（必须遵守，越靠前越重要）：
{preferences_text}

用户需求：{user_input}

请只输出一个 JSON 对象（不要用代码块包裹，不要输出解释文字）。

1. 请求工具（action）时输出：
{{"type":"action","tool":"工具名","input":"工具输入字符串"}}

2. 任务完成（final）时输出：
{{"type":"final","output":"最终回答（纯文本）"}}

**final.output** 必须是直接展示给用户的正文（Markdown/纯文本均可）；**禁止**把另一整段 `{{"type":"final","output":"..."}}` 当作字符串再嵌套进 `output`（套娃 JSON 会导致界面把整段协议原文显示给用户）。

输入字符串的换行规则：
- 若需要换行，请在 JSON 字符串内使用 `\\n` 表示（不要直接把换行字符写进 JSON 字符串）。
- 每轮只输出**一个**顶层 JSON 对象；用一对花括号正确闭合后**不要再多写**额外的闭括号，否则协议会解析失败并把整段 JSON 当成普通正文显示。

重要约束：
- **节省上下文（强约束）**：当用户曾在对话中粘贴大段设定原文、且相关内容已拆分/保存到 `data/` 时，**禁止**在后续各轮 JSON 的 `input` 或 `final.output` 中再次全文粘贴该长文；应改用 **ReadFile / SearchDocs / SettingsRoute** 按需读取少量文件。仅在用户明确要求「逐字引用原文」或单次短引用（建议不超过约 500 字）时，才可粘贴片段。
- 需要写入文件时，必须先输出一个 action：`tool`=WriteFile，并等待工具返回的 Observation；不得在未看到 WriteFile 的 Observation 之前以 final 声称已写入。
- 每一轮只能输出一个 JSON（要么 action 要么 final）。
- 当任务属于某个技能的典型能力（如“生成剧情大纲”）时，优先使用 RunSkill；否则优先直接用基础工具（ReadFile/WriteFile/LLM）。
- RunSkill 的 input 格式为「技能名|用户需求」：其中技能名可使用列表中的**规范 id**或括号内给出的**中文别名**（完全等价），例如 `大纲写手|一句话剧情` 与 `outline-writer|…` 相同。
- **多方案选型上下文（重要）**：以**最近一条助手消息**为准。若该消息只有**方案1/方案2**两组对白（dialogue-voice），用户点选后续写**对白**，须用 LLM + WriteFile，**禁止**调用 `outline-writer`；若用户消息含 `【对白】`（含系统自动追加的「【对白】【由系统根据上一轮助手输出自动标注】」），视为对白续写。若最近助手消息为**三套剧情大纲**（方案1–3），选型后续写**大纲**；**禁止**把对白选型误判为大纲、或对大纲选型调用 dialogue-voice。
- **大纲写手（outline-writer）**：仅用于把用户给出的**完整故事构思**一次性生成多套（如 3 个）大纲方案。**禁止**在历史对话里已经展示过「方案1/2/3」且用户正在**选择编号、要求展开/细化/保存某一方案**时再次调用 `RunSkill` 的大纲写手；此类续写应直接输出 `{{"type":"final","output":"…"}}`（合法的单一 JSON 对象），依据历史消息中已给出的方案正文扩展（必要时可先调用 LLM 再 final；需要落盘再用 WriteFile）。
- **角色设定写文件（强约束）**：当用户需求包含“人物设定/角色设定/角色卡/人设/小传/构思一个角色/保存到 data 并写成 md”等意图时，禁止调用 `outline-writer` 生成剧情大纲；应直接用 `LLM` 生成**短而结构化**的人物设定（默认 400–900 字），然后用 `WriteFile` 写入 `data/角色设定/<角色名>.md`（或用户指定的目录/文件名）。只有当用户明确要求“剧情大纲/主线/分支/多方案故事大纲”时才可调用 `outline-writer`。
- 当用户要求“修改具体字段/段落”（即不只是生成新文件）时，优先使用 SearchDocs 找到相关证据片段，再用 ReadFile 读取整文件并进行精确修改。
- 当用户要求“删除文件/移除某些文件”时，优先调用 DeleteFiles（或 DeleteFile）完成删除。
- 角色设定类内容默认写入到 data/角色设定/ 下；背景设定类内容默认写入到 data/背景设定/ 下。
- 如果你在向用户展示“多个方案供选择”（例如 outline-writer 生成了 3 个大纲），你必须在 final.output 中完整展示每个方案的正文（编号 + 标题 + 内容），禁止只给标题。
{prefs_flow_rule}

现在开始（你要输出第 1 轮 JSON）。"""


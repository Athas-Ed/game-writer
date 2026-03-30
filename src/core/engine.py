import json
import re
from typing import Any, Dict, List, Optional, Tuple

from src.core.policy import AgentRuntimeFlags, build_json_only_prompt, should_short_circuit_for_preferences
from src.core.app_context import AppContext
from src.core.tool_registry import (
    build_tool_registry,
    get_preferences_text,
    get_skills_catalog,
    normalize_write_path_for_tool,
)
from src.services.skills_service import resolve_skill_key
from src.tools.llm_tools import llm_generate

# DEBUG 下打印上下文时的分块大小（单块过大易淹没控制台，故长 prompt 采用 头+尾）
_DEBUG_PROMPT_CHUNK = 4000


def _parse_llm_decision(response: str) -> Dict[str, Any]:
    text = (response or "").strip()
    if not text:
        return {"type": "final", "output": ""}
    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}")
        json_candidate = text[start : end + 1]
    else:
        json_candidate = text
    try:
        data = json.loads(json_candidate)
    except Exception:
        return {"type": "final", "output": text}
    if not isinstance(data, dict):
        return {"type": "final", "output": str(data)}
    if data.get("type") == "action":
        return {"type": "action", "tool": data.get("tool"), "input": data.get("input", "")}
    if data.get("type") == "final":
        return {"type": "final", "output": data.get("output", "")}
    return {"type": "final", "output": text}


def _format_conversation_history(
    conversation_history: Optional[List[Dict[str, str]]],
    history_turns: int,
) -> str:
    if not conversation_history:
        return "无"
    valid_msgs = [
        m
        for m in conversation_history
        if isinstance(m, dict) and m.get("role") in {"user", "assistant"} and m.get("content")
    ]
    if not valid_msgs:
        return "无"
    max_msgs = max(0, history_turns * 2)
    sliced = valid_msgs[-max_msgs:] if max_msgs > 0 else []
    if not sliced:
        return "无"
    lines = []
    for msg in sliced:
        role = "用户" if msg["role"] == "user" else "助手"
        lines.append(f"{role}: {msg['content']}")
    return "\n".join(lines)


def run_agent_engine(
    *,
    user_input: str,
    max_steps: int,
    conversation_history: Optional[List[Dict[str, str]]],
    history_turns: int,
    flags: AgentRuntimeFlags,
    ctx: AppContext,
) -> str:
    # 偏好关闭时短路：避免后台跑工具
    if should_short_circuit_for_preferences(user_input, flags.prefs_enabled):
        return (
            "当前已关闭“偏好建议/写入”功能（PREFERENCES_WRITE_ENABLED=0）。\n\n"
            "如果你希望我把这条改良意见沉淀为长期偏好，请到「开发工具」中打开"
            "“允许 Agent 写入偏好（UpdatePreferences）”。"
        )

    tools = build_tool_registry(ctx)
    skills = get_skills_catalog(ctx)

    tool_descriptions = "\n".join(f"- {name}: {info['description']}" for name, info in tools.items())
    if skills:
        skill_lines: List[str] = []
        for meta in sorted(skills.values(), key=lambda x: str(x.get("name", ""))):
            desc = str(meta.get("description", ""))
            als = meta.get("aliases") or []
            if isinstance(als, list) and als:
                desc = f"{desc}（中文别名：{'、'.join(str(a) for a in als)}）"
            skill_lines.append(f"- {meta.get('name', '')}: {desc}")
        skill_descriptions = "\n".join(skill_lines)
    else:
        skill_descriptions = "- 无可用技能"
    history_text = _format_conversation_history(conversation_history, history_turns)
    preferences_text = get_preferences_text(ctx)

    current_prompt = build_json_only_prompt(
        tool_descriptions=tool_descriptions,
        skill_descriptions=skill_descriptions,
        history_text=history_text,
        preferences_text=preferences_text,
        history_turns=history_turns,
        user_input=user_input,
        prefs_enabled=flags.prefs_enabled,
    )

    repeated_action_count = 0
    last_action_signature: Optional[Tuple[str, str]] = None

    for step in range(max_steps):
        if flags.is_debug:
            plen = len(current_prompt)
            print(f"\n[DEBUG] === Step {step + 1} — 发给模型的上下文长度: {plen} 字符 ===")
            if plen <= _DEBUG_PROMPT_CHUNK * 2:
                print(f"[DEBUG] Full prompt:\n{current_prompt}")
            else:
                omit = plen - 2 * _DEBUG_PROMPT_CHUNK
                print(
                    f"[DEBUG] Prompt head ({_DEBUG_PROMPT_CHUNK} chars):\n{current_prompt[:_DEBUG_PROMPT_CHUNK]}\n"
                    f"... [已省略中间 {omit} 字符] ...\n"
                    f"[DEBUG] Prompt tail ({_DEBUG_PROMPT_CHUNK} chars):\n{current_prompt[-_DEBUG_PROMPT_CHUNK:]}"
                )

        response = llm_generate(current_prompt)
        if flags.is_info:
            print(f"\n--- Step {step + 1} ---")
            if flags.is_debug:
                print("LLM Response:\n", response)
            print("-" * 40)

        decision = _parse_llm_decision(response)
        if flags.is_debug:
            try:
                dbg_decision = json.dumps(decision, ensure_ascii=False)
            except (TypeError, ValueError):
                dbg_decision = str(decision)
            print(f"[DEBUG] Parsed decision: {dbg_decision}")

        if decision.get("type") == "action":
            tool_name = decision.get("tool")
            tool_input = decision.get("input", "")

            if tool_name is None:
                current_prompt += "\nObservation: action 缺少 tool 字段。\n"
                continue

            if not flags.prefs_enabled and tool_name in {"ProposePreference", "UpdatePreferences", "ListPreferences"}:
                return (
                    "当前已关闭“偏好建议/写入”功能（PREFERENCES_WRITE_ENABLED=0）。\n\n"
                    "如果你希望我把改良意见写入偏好文件，请到「开发工具」中打开写入开关后再试。"
                )

            if flags.is_info:
                tin = str(tool_input)
                if flags.is_debug:
                    print(f"[DEBUG] Action: tool={tool_name!r}, input (full, {len(tin)} chars):\n{tin}")
                else:
                    print(f"Action match: {tool_name}, Input (truncated): {tin[:120]}{'...' if len(tin) > 120 else ''}")

            action_signature = (tool_name, str(tool_input))
            if action_signature == last_action_signature:
                repeated_action_count += 1
            else:
                repeated_action_count = 0
            last_action_signature = action_signature

            if tool_name not in tools:
                current_prompt += f"\nObservation: 未知工具 '{tool_name}'\n"
                continue

            try:
                if tool_name == "WriteFile":
                    if "|" not in str(tool_input):
                        result = "WriteFile 输入格式错误：需要「相对路径|正文」，且必须包含一个竖线。"
                    else:
                        file_path, content = str(tool_input).split("|", 1)
                        file_path = normalize_write_path_for_tool(ctx, file_path)
                        content = content.lstrip().replace("\\n", "\n")
                        if flags.is_debug:
                            print(f"[DEBUG] WriteFile path: {file_path!r}, content len: {len(content)}")
                        result = tools[tool_name]["func"](file_path, content)
                else:
                    if isinstance(tool_input, str):
                        tool_input = tool_input.replace("\\n", "\n")
                    result = tools[tool_name]["func"](str(tool_input))

                # 对 outline-writer：优先把 3 个方案“原样完整展示”给 UI，
                # 避免 LLM 二次转述时只保留标题导致用户无法辨别。
                if tool_name == "RunSkill":
                    payload = str(tool_input)
                    head = payload.split("|", 1)[0].strip() if "|" in payload else ""
                    canon_skill = resolve_skill_key(head, skills) if head else None
                    if canon_skill == "outline-writer" and "方案1" in str(result) and "方案2" in str(result):
                        if flags.is_info:
                            if flags.is_debug:
                                print(f"[DEBUG] Observation (outline-writer short-circuit, full):\n{result}")
                            else:
                                r = str(result)
                                print(
                                    f"Observation (short-circuit): {r[:800]}{'…' if len(r) > 800 else ''} "
                                    f"（全文 {len(r)} 字符；设 AGENT_LOG_LEVEL=DEBUG 可打印全文）"
                                )
                        return f"{result}\n\n请回复你选择的方案编号（1/2/3），我会把该方案整理成完整 Markdown 并按你指定的文件名保存。"
                    if canon_skill == "dialogue-voice" and "方案1" in str(result) and "方案2" in str(result):
                        if flags.is_info:
                            if flags.is_debug:
                                print(f"[DEBUG] Observation (dialogue-voice short-circuit, full):\n{result}")
                            else:
                                r = str(result)
                                print(
                                    f"Observation (short-circuit): {r[:800]}{'…' if len(r) > 800 else ''} "
                                    f"（全文 {len(r)} 字符；DEBUG 可打印全文）"
                                )
                        return f"{result}\n\n请回复你选择的方案编号（1/2），我会按该组对白继续润色、扩展或按你指定方式保存。"

                if flags.is_info:
                    if flags.is_debug:
                        print(f"[DEBUG] Observation (full):\n{result}")
                    else:
                        r = str(result)
                        print(f"Observation: {r[:800]}{'…' if len(r) > 800 else ''} （全文 {len(r)} 字符）")
                current_prompt += f"\n{response}\nObservation: {result}\n"

                if repeated_action_count >= 2:
                    current_prompt += (
                        "Observation: 你连续多次执行了相同 Action。"
                        "请基于已有 Observation 调整策略，或直接给出 type=final 的 JSON。\n"
                    )
            except Exception as e:
                current_prompt += f"\nObservation: 调用工具 {tool_name} 时出错: {e}\n"
            continue

        if decision.get("type") == "final":
            final_output = str(decision.get("output", "")).strip()
            if flags.is_info:
                print("\n=== Final Answer ===")
                print(final_output)
                print("====================")
            return final_output

        return (response or "").strip()

    timeout_msg = (
        "达到最大步数，任务可能未完成。"
        "请尝试提高 max_steps，或让模型在无法获取文件信息时直接给出说明性最终答案。"
    )
    if flags.is_info:
        print("\n=== Final Output (max steps reached) ===")
        print(timeout_msg)
        print("========================================")
    return timeout_msg


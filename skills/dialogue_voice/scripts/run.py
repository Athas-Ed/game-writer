from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

PROJECT_ROOT = SCRIPT_DIR.parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from generate_dialogue import generate_dialogue_two_variants
from parse_request import parse_dialogue_request, retrieval_seed

from src.tools.setting_context import read_settings_for_retrieval


def run(input_text: str) -> str:
    """
    dialogue-voice 技能：根据场景与可选参数生成两组对白（方案1/方案2）。
    """
    raw_in = (input_text or "").strip()
    if not raw_in:
        return (
            "dialogue-voice 输入为空。\n"
            "请描述场景与冲突；可选用单独一行：\n"
            "- speakers=林夕,木子（或 角色=…）\n"
            "- tone=口语化,克制\n"
            "- format=纯对白 / 带【旁白】\n"
        )

    req = parse_dialogue_request(raw_in)
    if not req.scene:
        return "dialogue-voice：未识别到场景正文。请在可选行之后写出「谁在什么情况下说什么」的需求。"

    seed = retrieval_seed(req)
    context = read_settings_for_retrieval(seed)
    llm_raw, blocks = generate_dialogue_two_variants(req, context)

    if len(blocks) >= 2:
        lines = ["已执行技能 dialogue-voice，生成 2 组对白方案（语气/节奏不同）："]
        for i, body in enumerate(blocks[:2], start=1):
            lines.append(f"\n方案{i}:\n{body.strip()}")
        return "\n".join(lines)

    if len(blocks) == 1:
        return (
            "已执行技能 dialogue-voice（模型未严格分出两方案，以下为解析结果 + 原文备查）：\n\n"
            f"方案1:\n{blocks[0]}\n\n--- 原始输出 ---\n{llm_raw}"
        )

    return (
        "已执行技能 dialogue-voice（未解析到「方案1/方案2」结构，以下为模型全文）：\n\n"
        + llm_raw
    )

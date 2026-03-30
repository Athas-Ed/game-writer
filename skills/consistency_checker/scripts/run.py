from __future__ import annotations

from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

PROJECT_ROOT = SCRIPT_DIR.parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from check_consistency import run_consistency_check
from load_context import build_check_context, parse_options_and_hint


def run(input_text: str) -> str:
    """
    setting-consistency 技能入口。
    用户需求中可写可选行（可单独成行）：
    - focus=关键词1,关键词2 — 先检索相关分块再附广泛节选
    - dirs=角色设定 或 scope=角色设定,背景设定 — 限定 read_settings_bundle 的目录（默认 角色设定+背景设定）
    其余行作为「检查侧重点」交给模型。
    """
    raw = (input_text or "").strip()
    if not raw:
        return (
            "setting-consistency 输入为空。\n"
            "示例：\n"
            "- 全盘检查时间线与年龄\n"
            "- focus=林夕,月台\ndirs=角色设定\n重点核对出场年龄与事件顺序"
        )

    opts, hint = parse_options_and_hint(raw)
    context, note = build_check_context(raw)
    header = f"已执行技能 setting-consistency（{note}）。\n\n---\n\n"
    report = run_consistency_check(context, user_hint=hint)
    return header + report

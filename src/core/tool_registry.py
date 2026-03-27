from typing import Any, Dict

from src.tools.llm_tools import llm_generate
from src.tools.file_tools import delete_directory, delete_file, delete_files, read_file, write_file
from src.tools.search_docs import search_docs

from src.services.llm_env_service import get_llm_env_summary
from src.services.output_path_service import normalize_write_path
from src.services.preferences_service import append_preference_rule, load_preferences_text, propose_preference
from src.services.skills_service import diagnose_skills as diagnose_skills_impl, run_skill as run_skill_impl, scan_skills

from src.core.app_context import AppContext

def get_skills_catalog(ctx: AppContext) -> Dict[str, Dict[str, str]]:
    return dict(scan_skills(ctx.skills_root))


def get_preferences_text(ctx: AppContext) -> str:
    return load_preferences_text(ctx.preferences_path)


def update_preferences(ctx: AppContext, rule_text: str) -> str:
    res = append_preference_rule(ctx.preferences_path, rule_text)
    return res.message


def run_skill(ctx: AppContext, payload: str) -> str:
    return run_skill_impl(payload, ctx.skills_state, ctx.skills_root)


def diagnose_skills(ctx: AppContext) -> list[dict[str, Any]]:
    return diagnose_skills_impl(ctx.project_root, ctx.skills_root)


def build_tool_registry(ctx: AppContext) -> Dict[str, Dict[str, Any]]:
    # 以函数形式返回，避免 import 时顺序问题
    return {
        "ReadFile": {
            "func": read_file,
            "description": "读取文件内容。输入：文件路径（相对项目根目录）",
        },
        "WriteFile": {
            "func": write_file,
            "description": (
                "写入文件。输入是一个字符串：相对路径|正文全文（仅第一个竖线分隔路径与内容）。"
                "如正文需要换行，请在 JSON 字符串里用 \\n 表示（不要直接写多行进入 JSON）。"
                "建议始终写入 data/ 下，例如 data/角色设定/林夕.md|她是一名温柔的学姐……"
            ),
        },
        "DeleteFile": {
            "func": lambda payload: delete_file(str(payload)),
            "description": (
                "删除单个文件（相对项目根目录）。默认仅允许删除 data/ 下的文件。"
                "输入：文件路径（例如 data/角色设定/林夕.md）。"
            ),
        },
        "DeleteFiles": {
            "func": lambda payload: delete_files(str(payload)),
            "description": (
                "删除多个文件（相对项目根目录）。默认仅允许删除 data/ 下的文件。"
                "输入：文件路径列表（可多行/用逗号或分号分隔），例如：data/角色设定/林夕.md\\ndata/角色设定/木子夕.md"
            ),
        },
        "DeleteDirectory": {
            "func": lambda payload: delete_directory(str(payload)),
            "description": (
                "删除目录（相对项目根目录）。默认仅允许删除 data/ 下的目录。"
                "默认不递归：目录非空会失败。"
                "输入示例：data/背景设定/临时 或 path=data/背景设定/临时 recursive=true"
            ),
        },
        "SearchDocs": {
            "func": lambda payload: search_docs(payload),
            "description": (
                "在 data/**/*.md 中做字段/段落级证据检索（返回 top-k 片段，含文件路径/标题/片段内容）。"
                "输入：query（例如“艾莉丝 年龄 18”或“艾莉丝 年龄”）。"
                "可升级为向量+RAG，支持处理上万的md文件。"
            ),
        },
        "LLM": {"func": lambda prompt: llm_generate(prompt), "description": "调用语言模型进行文本创作。输入：提示词"},
        "RunSkill": {
            "func": lambda payload: run_skill(ctx, payload),
            "description": (
                "执行已加载技能。输入格式：技能名|用户需求。"
                "如用户需求需要换行，请在 JSON 字符串里用 \\n 表示。"
                "例如：outline-writer|主角在废弃车站发现一封旧信。"
            ),
        },
        "ListPreferences": {
            "func": lambda _payload: get_preferences_text(ctx),
            "description": "读取当前项目偏好（config/preferences.md）。输入可留空。",
        },
        "ProposePreference": {
            "func": lambda payload: propose_preference(payload),
            "description": "将用户的改良意见归纳成一条可写入的偏好规则（不会落盘）。输入：用户原话。",
        },
        "UpdatePreferences": {
            "func": lambda payload: update_preferences(ctx, payload),
            "description": "将一条偏好规则追加写入 config/preferences.md，并自动查重。输入：一条规则文本。",
        },
    }


def normalize_write_path_for_tool(ctx: AppContext, file_path: str) -> str:
    ctx.refresh_output_targets()
    return normalize_write_path(file_path, ctx.output_targets_cache)


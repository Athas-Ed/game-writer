from typing import Any, Dict

from src.tools.llm_tools import llm_generate
from src.tools.file_tools import delete_directory, delete_file, delete_files, read_file, write_file
from src.tools.search_docs import search_docs
from src.tools.settings_route import settings_route
from src.tools.vector_tools import build_vector_index, vector_search

from src.services.llm_env_service import get_llm_env_summary
from src.services.output_path_service import normalize_write_path
from src.services.preferences_service import append_preference_rule, load_preferences_text, propose_preference
from src.services.skills_service import diagnose_skills as diagnose_skills_impl, run_skill as run_skill_impl, scan_skills

from src.core.app_context import AppContext

def get_skills_catalog(ctx: AppContext) -> Dict[str, Dict[str, Any]]:
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
                "在 data/**/*.md 中做字段/段落级证据检索（返回 top-k 片段，含 chunk_ref/data_category/标题/片段）。"
                "输入：query 字符串（例如“艾莉丝 年龄 18”）。"
                "大范围浏览请先用 SettingsRoute list 或 files dir=…。"
            ),
        },
        "VectorSearch": {
            "func": lambda payload: vector_search(str(payload)),
            "description": (
                "向量语义检索：在 data/ Markdown 分块上做 embedding 相似度检索，返回 top-k 相关 chunk。"
                "输出包含 chunk_ref、来源文件与正文片段。"
                "输入：query 字符串（也可写成 query=...|top_k=8）。"
                "下一步：用 ReadFile 读取对应文件，并按 chunk_ref 精确定位修改。"
            ),
        },
        "BuildVectorIndex": {
            "func": lambda payload: build_vector_index(str(payload)),
            "description": (
                "构建/重建向量索引（持久化到 .vector_index/），用于确保 VectorSearch 可用且索引最新。"
                "输入可选：force=true/1（强制重建）。"
                "输出会返回 collection 名与条目数 count。"
            ),
        },
        "SettingsRoute": {
            "func": lambda payload: settings_route(str(payload)),
            "description": (
                "设定库结构化路由：list 列索引；files dir=角色设定 列目录下全部 md；"
                "chunks path=data/…/某.md 输出分块+元数据（chunk_ref）；search 关键词 同 SearchDocs。"
                "输入示例单行：list | files dir=背景设定/种族 | chunks path=data/角色设定/林夕.md | search 林夕"
            ),
        },
        "LLM": {"func": lambda prompt: llm_generate(prompt), "description": "调用语言模型进行文本创作。输入：提示词"},
        "RunSkill": {
            "func": lambda payload: run_skill(ctx, payload),
            "description": (
                "执行已加载技能。输入格式：技能名|用户需求（技能名可用规范 id 或 SKILL.md 中的中文别名，见技能列表括号内）。"
                "如用户需求需要换行，请在 JSON 字符串里用 \\n 表示。"
                "例如：outline-writer|主角在废弃车站发现一封旧信。或：大纲写手|同左。"
                "注意：用户已选「方案1/2/3」并要求展开细化时，不要再调用 outline-writer，应直接 final 续写。"
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


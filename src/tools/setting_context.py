"""
技能共用的「检索优先 + 广泛节选」设定加载，与 SearchDocs 同源分块索引。
"""

from __future__ import annotations

from src.tools.file_tools import read_settings_bundle
from src.tools.search_docs import gather_evidence_context


def read_settings_for_retrieval(seed_text: str) -> str:
    """
    用一段种子文本（剧情句、角色名、场景关键词等）检索 data/**/*.md 分块，
    再拼接截断后的广泛设定节选；无命中时退回整包 read_settings_bundle()。
    """
    seed = (seed_text or "").strip()
    if not seed:
        return read_settings_bundle()

    evidence = gather_evidence_context(seed, top_k=16, max_total_chars=26_000)
    if not evidence:
        return (
            "【说明】按种子文本在 data/**/*.md 中检索未命中分块（关键词不在设定中、内容过短未分块、或库为空）。\n"
            "已退回为广泛读取设定目录。\n\n"
            + read_settings_bundle()
        )

    bundle = read_settings_bundle(max_total_chars=36_000, max_files_per_dir=120)
    return (
        "## 与种子文本相关的设定（检索优先：完整分块）\n\n"
        + evidence
        + "\n\n---\n\n## 设定库广泛节选（兜底与全局约束）\n\n"
        + bundle
    )

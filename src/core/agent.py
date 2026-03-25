"""
兼容入口：保留 `src.core.agent` 的对外 API（供 UI/外部导入）。

该文件必须保持“薄封装”，核心实现位于：
- `src.core.engine`
- `src.core.policy`
- `src.core.tool_registry`
"""

from typing import Dict, List, Optional

from src.core.app_context import default_context
from src.core.engine import run_agent_engine
from src.core.policy import get_runtime_flags
from src.core.tool_registry import diagnose_skills as diagnose_skills_impl, get_llm_env_summary, get_skills_catalog as get_skills_catalog_impl


_CTX = default_context()


def run_agent(
    user_input: str,
    max_steps: int = 8,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    history_turns: int = 6,
) -> str:
    flags = get_runtime_flags()
    return run_agent_engine(
        user_input=user_input,
        max_steps=max_steps,
        conversation_history=conversation_history,
        history_turns=history_turns,
        flags=flags,
        ctx=_CTX,
    )


def get_skills_catalog():
    return get_skills_catalog_impl(_CTX)


def diagnose_skills():
    return diagnose_skills_impl(_CTX)


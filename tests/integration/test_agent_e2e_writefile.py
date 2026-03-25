import os
from pathlib import Path

import pytest


@pytest.mark.integration
def test_agent_e2e_writefile_real_llm(tmp_path: Path, monkeypatch):
    """
    可选集成测试（会走网络/消耗额度）：
    - 让 Agent 只做一次 WriteFile 并结束
    - 验证工具链不会卡死
    """
    if os.getenv("RUN_INTEGRATION_TESTS", "0") != "1":
        pytest.skip("integration test disabled (set RUN_INTEGRATION_TESTS=1 to enable)")
    if not os.getenv("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set")

    # 将写入路径映射到 tmp_path，避免污染真实 data/
    import src.core.tool_registry as tr

    def write_file_to_tmp(file_path: str, content: str) -> str:
        target = tmp_path / file_path.replace("\\", "/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"已写入: {file_path}"

    # 使用 build_tool_registry(ctx) 生成工具表，并替换 WriteFile 为 tmp 写入
    ctx = tr.default_context()
    tools = tr.build_tool_registry(ctx)
    tools["WriteFile"]["func"] = write_file_to_tmp

    # monkeypatch engine 取工具表的函数，使其使用我们替换后的 WriteFile
    import src.core.engine as engine

    # 让 engine 使用我们替换后的工具表
    monkeypatch.setattr(engine, "build_tool_registry", lambda _ctx: tools)
    monkeypatch.setenv("AGENT_LOG_LEVEL", "NONE")

    from src.core.policy import AgentRuntimeFlags

    out = engine.run_agent_engine(
        user_input="请只输出一个 action：WriteFile，把内容 hello 写入 角色设定/integration_hello.md，然后输出 final。",
        max_steps=4,
        conversation_history=[],
        history_turns=0,
        flags=AgentRuntimeFlags(log_level="NONE", prefs_enabled=True),
        ctx=ctx,
    )

    assert isinstance(out, str) and out.strip()
    # 允许两种落点（取决于 output_targets 映射是否触发）
    candidates = [
        tmp_path / "data/角色设定/integration_hello.md",
        tmp_path / "角色设定/integration_hello.md",
    ]
    assert any(p.exists() for p in candidates)


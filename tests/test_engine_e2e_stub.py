import itertools
from pathlib import Path

from src.core.app_context import AppContext
from src.core.policy import AgentRuntimeFlags


def test_engine_end_to_end_writefile_with_stub_llm(monkeypatch, tmp_path: Path):
    """
    端到端（稳定版，不走网络）：
    - stub llm_generate 依次返回 action->final
    - stub tool registry 的 WriteFile 真实写入 tmp_path
    - 验证 engine 循环能执行工具并返回 final
    """
    # --- stub llm ---
    replies = itertools.chain(
        [
            '{"type":"action","tool":"WriteFile","input":"角色设定/冒烟_stub.md|hello"}',
            '{"type":"final","output":"ok"}',
        ]
    )

    def fake_llm_generate(_prompt: str, temperature: float = 0.7) -> str:  # noqa: ARG001
        return next(replies)

    # --- stub tools ---
    written: list[Path] = []

    def write_file_stub(file_path: str, content: str) -> str:
        # 将相对路径写入 tmp_path 下，模拟项目写文件
        target = tmp_path / file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(target)
        return f"已写入: {file_path}"

    def build_tool_registry_stub(_ctx: AppContext):
        return {
            "WriteFile": {"func": write_file_stub, "description": "stub"},
            "ReadFile": {"func": lambda p: "", "description": "stub"},
            "LLM": {"func": lambda p: "", "description": "stub"},
            "RunSkill": {"func": lambda p: "", "description": "stub"},
            "ListPreferences": {"func": lambda p: "无", "description": "stub"},
            "ProposePreference": {"func": lambda p: p, "description": "stub"},
            "UpdatePreferences": {"func": lambda p: "ok", "description": "stub"},
            "DeleteFile": {"func": lambda p: "ok", "description": "stub"},
            "DeleteFiles": {"func": lambda p: "ok", "description": "stub"},
            "SearchDocs": {"func": lambda p: "ok", "description": "stub"},
        }

    def normalize_write_path_stub(_ctx: AppContext, p: str) -> str:
        # 模拟口语目录映射：角色设定 -> data/角色设定
        p = p.replace("\\", "/").lstrip("./")
        if p.startswith("角色设定/"):
            return "data/" + p
        return p

    # --- monkeypatch engine dependencies ---
    import src.core.engine as engine

    monkeypatch.setattr(engine, "llm_generate", fake_llm_generate)
    monkeypatch.setattr(engine, "build_tool_registry", build_tool_registry_stub)
    monkeypatch.setattr(engine, "get_skills_catalog", lambda _ctx: {"outline-writer": {"name": "outline-writer", "description": "stub"}})
    monkeypatch.setattr(engine, "get_preferences_text", lambda _ctx: "无")
    monkeypatch.setattr(engine, "normalize_write_path_for_tool", normalize_write_path_stub)

    out = engine.run_agent_engine(
        user_input="写入文件",
        max_steps=3,
        conversation_history=[],
        history_turns=0,
        flags=AgentRuntimeFlags(log_level="NONE", prefs_enabled=True),
        ctx=AppContext(
            project_root=tmp_path,
            skills_root=tmp_path / "skills",
            config_root=tmp_path / "config",
            data_root=tmp_path / "data",
            output_targets_path=tmp_path / "config/output_targets.json",
            preferences_path=tmp_path / "config/preferences.md",
        ),
    )

    assert out == "ok"
    assert written, "expected WriteFile to be executed"
    assert written[0].read_text(encoding="utf-8") == "hello"


def test_engine_end_to_end_runskill_with_stub_llm(monkeypatch):
    """
    端到端（稳定版，不走网络）：
    - action RunSkill -> final
    - 验证循环能调用工具并结束
    """
    replies = iter(
        [
            '{"type":"action","tool":"RunSkill","input":"outline-writer|一句话剧情"}',
            # 由于 engine 对 outline-writer 会优先原样展示方案并直接 return，
            # 该条回复理论上不会被消费；保留以防未来逻辑回退。
            '{"type":"final","output":"请选择 1/2/3"}',
        ]
    )

    def fake_llm_generate(_prompt: str, temperature: float = 0.7) -> str:  # noqa: ARG001
        return next(replies)

    called = {"runs": 0}

    def run_skill_stub(payload: str) -> str:
        called["runs"] += 1
        assert payload.startswith("outline-writer|")
        return "方案1: ...\n方案2: ...\n方案3: ..."

    def build_tool_registry_stub(_ctx: AppContext):
        return {
            "RunSkill": {"func": run_skill_stub, "description": "stub"},
            "WriteFile": {"func": lambda p, c: "ok", "description": "stub"},
            "ReadFile": {"func": lambda p: "", "description": "stub"},
            "LLM": {"func": lambda p: "", "description": "stub"},
            "ListPreferences": {"func": lambda p: "无", "description": "stub"},
            "ProposePreference": {"func": lambda p: p, "description": "stub"},
            "UpdatePreferences": {"func": lambda p: "ok", "description": "stub"},
            "DeleteFile": {"func": lambda p: "ok", "description": "stub"},
            "DeleteFiles": {"func": lambda p: "ok", "description": "stub"},
            "SearchDocs": {"func": lambda p: "ok", "description": "stub"},
        }

    import src.core.engine as engine

    monkeypatch.setattr(engine, "llm_generate", fake_llm_generate)
    monkeypatch.setattr(engine, "build_tool_registry", build_tool_registry_stub)
    monkeypatch.setattr(engine, "get_skills_catalog", lambda _ctx: {"outline-writer": {"name": "outline-writer", "description": "stub"}})
    monkeypatch.setattr(engine, "get_preferences_text", lambda _ctx: "无")
    monkeypatch.setattr(engine, "normalize_write_path_for_tool", lambda _ctx, p: p)

    out = engine.run_agent_engine(
        user_input="生成大纲",
        max_steps=3,
        conversation_history=[],
        history_turns=0,
        flags=AgentRuntimeFlags(log_level="NONE", prefs_enabled=True),
        ctx=AppContext(
            project_root=Path("."),
            skills_root=Path("skills"),
            config_root=Path("config"),
            data_root=Path("data"),
            output_targets_path=Path("config/output_targets.json"),
            preferences_path=Path("config/preferences.md"),
        ),
    )

    assert "方案1" in out and "方案2" in out and "方案3" in out
    assert "1/2/3" in out
    assert called["runs"] == 1


"""引擎侧对话/多步回溯长度控制（省 Token）。"""

import json

import pytest

import src.core.engine as engine


def test_format_conversation_history_truncates_long_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "_HISTORY_MSG_MAX_CHARS", 200)
    long_user = "U" * 500
    hist = [{"role": "user", "content": long_user}]
    out = engine._format_conversation_history(hist, history_turns=6)
    assert "UU" in out
    assert "省略" in out or "缩短" in out
    assert len(out) < len(long_user) + 50


def test_format_conversation_history_respects_zero_as_unlimited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "_HISTORY_MSG_MAX_CHARS", 0)
    long_user = "Z" * 8000
    hist = [{"role": "user", "content": long_user}]
    out = engine._format_conversation_history(hist, history_turns=6)
    assert out.endswith("ZZ")


def test_compact_action_json_shortens_long_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "_SCRATCHPAD_ACTION_INPUT_MAX_CHARS", 120)
    pad = "X" * 400
    raw = json.dumps({"type": "action", "tool": "LLM", "input": pad}, ensure_ascii=False)
    compacted = engine._compact_action_json_for_scratchpad(raw)
    data = json.loads(compacted)
    assert data["type"] == "action"
    assert len(data["input"]) < len(pad)
    assert "压缩" in data["input"] or "省略" in data["input"]


def test_compact_action_json_skips_setting_splitter_runskill(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "_SCRATCHPAD_ACTION_INPUT_MAX_CHARS", 80)
    payload = "setting-splitter|" + "Z" * 500
    raw = json.dumps({"type": "action", "tool": "RunSkill", "input": payload}, ensure_ascii=False)
    assert engine._compact_action_json_for_scratchpad(raw) == raw


def test_compact_action_json_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "_SCRATCHPAD_ACTION_INPUT_MAX_CHARS", 0)
    pad = "Y" * 500
    raw = json.dumps({"type": "action", "tool": "LLM", "input": pad}, ensure_ascii=False)
    assert engine._compact_action_json_for_scratchpad(raw) == raw


def test_truncate_observation_for_scratchpad(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "_OBSERVATION_MAX_CHARS", 300)
    obs = "O" * 2000
    cut = engine._truncate_observation_for_scratchpad(obs)
    assert len(cut) < len(obs)
    assert "省略" in cut

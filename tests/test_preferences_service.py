from pathlib import Path

from src.services.preferences_service import append_preference_rule, load_preferences_text


def test_append_preference_dedup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PREFERENCES_WRITE_ENABLED", "1")
    pref = tmp_path / "preferences.md"

    r1 = append_preference_rule(pref, "以后输出 4 个方案")
    assert r1.ok
    r2 = append_preference_rule(pref, "- 以后输出 4 个方案")
    assert not r2.ok

    text = load_preferences_text(pref)
    assert "以后输出 4 个方案" in text


def test_append_preference_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PREFERENCES_WRITE_ENABLED", "0")
    pref = tmp_path / "preferences.md"
    r = append_preference_rule(pref, "x")
    assert not r.ok


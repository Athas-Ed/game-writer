from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Set


@dataclass(frozen=True)
class PreferencesResult:
    ok: bool
    message: str


def preferences_enabled() -> bool:
    """是否启用偏好建议/写入功能（只受开关影响）。"""
    return os.getenv("PREFERENCES_WRITE_ENABLED", "1").strip() != "0"


def load_preferences_text(preferences_path: Path) -> str:
    try:
        if preferences_path.exists():
            text = preferences_path.read_text(encoding="utf-8").strip()
            return text if text else "无"
    except Exception:
        pass
    return "无"


def propose_preference(user_text: str) -> str:
    if not preferences_enabled():
        return "（偏好功能已关闭）"
    t = (user_text or "").strip()
    if not t:
        return "（空）"
    for prefix in ("偏好：", "偏好:", "约束：", "约束:", "规则：", "规则:", "建议：", "建议:"):
        if t.startswith(prefix):
            t = t[len(prefix) :].strip()
            break
    return t


def _normalize_pref_line(rule: str) -> str:
    s = (rule or "").strip()
    if s.startswith("- "):
        s = s[2:].strip()
    elif s.startswith("* "):
        s = s[2:].strip()
    return " ".join(s.split())


def _existing_rules_set(existing_md: str) -> Set[str]:
    existing_norm: Set[str] = set()
    for line in (existing_md or "").splitlines():
        ln = _normalize_pref_line(line)
        if ln:
            existing_norm.add(ln)
    return existing_norm


def append_preference_rule(preferences_path: Path, rule_text: str) -> PreferencesResult:
    """
    追加偏好规则到 preferences.md（自动查重）。
    """
    if not preferences_enabled():
        return PreferencesResult(ok=False, message="已拒绝：偏好写入开关已关闭（PREFERENCES_WRITE_ENABLED=0）。")

    rule = _normalize_pref_line(rule_text)
    if not rule:
        return PreferencesResult(ok=False, message="未写入：规则为空。")

    existing = ""
    try:
        if preferences_path.exists():
            existing = preferences_path.read_text(encoding="utf-8")
    except Exception:
        existing = ""

    if rule in _existing_rules_set(existing):
        return PreferencesResult(ok=False, message="未写入：该偏好已存在（查重命中）。")

    preferences_path.parent.mkdir(parents=True, exist_ok=True)
    to_append = f"\n- {rule}\n"
    if not existing.strip():
        header = "## 默认偏好\n"
        preferences_path.write_text(header + to_append.lstrip("\n"), encoding="utf-8")
    else:
        preferences_path.write_text(existing.rstrip() + to_append, encoding="utf-8")

    return PreferencesResult(ok=True, message="已写入：偏好规则已追加到 config/preferences.md")


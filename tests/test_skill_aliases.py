from pathlib import Path

from src.services.skills_service import (
    build_alias_map,
    resolve_skill_key,
    scan_skills,
    _parse_aliases_line,
)


def test_parse_aliases_line():
    text = """---
name: x
aliases: 甲, 乙、丙
description: d
---"""
    assert _parse_aliases_line(text) == ["甲", "乙", "丙"]
    fm = "---\nname: z\n别名：foo｜bar\ndescription: d\n---"
    assert _parse_aliases_line(fm) == ["foo", "bar"]


def test_resolve_skill_key_with_scan(tmp_path: Path):
    skills_dir = tmp_path / "skills" / "demo_skill"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\n"
        "name: demo-skill\n"
        "aliases: 演示, 小演示\n"
        "description: test\n"
        "---\n",
        encoding="utf-8",
    )
    cat = scan_skills(tmp_path / "skills")
    assert resolve_skill_key("demo-skill", cat) == "demo-skill"
    assert resolve_skill_key("DEMO-SKILL", cat) == "demo-skill"
    assert resolve_skill_key("演示", cat) == "demo-skill"
    assert resolve_skill_key("小演示", cat) == "demo-skill"
    assert resolve_skill_key("不存在", cat) is None


def test_build_alias_map_first_wins():
    cat = {
        "a": {"name": "a", "aliases": ["共享"]},
        "b": {"name": "b", "aliases": ["共享", "乙"]},
    }
    m = build_alias_map(cat)
    assert m["共享"] == "a"
    assert m["乙"] == "b"

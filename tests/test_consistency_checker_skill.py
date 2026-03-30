"""consistency_checker 技能：解析选项与组装上下文（不调用真实 LLM）。"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def cc_load_context():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    path = ROOT / "skills/consistency_checker/scripts/load_context.py"
    spec = importlib.util.spec_from_file_location("cc_load_context", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parse_options_and_hint(cc_load_context):
    opts, hint = cc_load_context.parse_options_and_hint(
        "focus=A,B\ndirs=角色设定\n只看时间线\n第二行提示"
    )
    assert opts["focus"] == ["A", "B"]
    assert opts["dirs"] == ["角色设定"]
    assert "时间线" in hint and "第二行" in hint


def test_parse_scope_chinese(cc_load_context):
    opts, hint = cc_load_context.parse_options_and_hint("范围=背景设定/种族")
    assert opts["dirs"] == ["背景设定/种族"]
    assert hint == ""


def test_build_check_context_focus_hits(tmp_path, monkeypatch, cc_load_context):
    from src.tools.data_chunks import invalidate_data_chunks_cache

    root = tmp_path
    data = root / "data" / "角色设定"
    data.mkdir(parents=True)
    long_body = "详细设定内容。" * 80
    (data / "测试角色.md").write_text(f"## 基础信息\n\n{long_body}\n", encoding="utf-8")
    monkeypatch.setattr("src.tools.file_tools.PROJECT_ROOT", root)
    monkeypatch.setattr("src.tools.data_chunks.PROJECT_ROOT", root)
    monkeypatch.setattr("src.tools.data_chunks.DATA_ROOT", root / "data")
    invalidate_data_chunks_cache()

    ctx, note = cc_load_context.build_check_context("focus=测试角色")
    assert "focus" in note.lower() or "检索" in note
    assert "data/角色设定/测试角色.md" in ctx or "基础信息" in ctx


def test_run_consistency_empty_corpus():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    p = ROOT / "skills/consistency_checker/scripts/check_consistency.py"
    spec = importlib.util.spec_from_file_location("cc_check", p)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = mod.run_consistency_check("   ")
    assert "为空" in out

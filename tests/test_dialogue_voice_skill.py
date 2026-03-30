import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/dialogue_voice/scripts"


@pytest.fixture
def dv_scripts():
    p = str(SCRIPTS)
    if p not in sys.path:
        sys.path.insert(0, p)
    import generate_dialogue as gd  # noqa: WPS433
    import parse_request as pr  # noqa: WPS433

    return pr, gd


def test_parse_dialogue_request(dv_scripts):
    pr, _ = dv_scripts
    text = """speakers=林夕,艾莉
tone=克制
这里是车站对峙场景，两人试探来信来源。
"""
    r = pr.parse_dialogue_request(text)
    assert r.speakers == ["林夕", "艾莉"]
    assert "克制" in r.tone_hints[0]
    assert "车站" in r.scene
    assert pr.retrieval_seed(r) == "林夕 艾莉 这里是车站对峙场景，两人试探来信来源。"


def test_split_scheme_blocks(dv_scripts):
    _, gd = dv_scripts
    raw = """方案1：
A版
对白一行

方案2：
B版
对白两行
"""
    blocks = gd._split_scheme_blocks(raw)
    assert len(blocks) == 2
    assert "A版" in blocks[0] and "B版" in blocks[1]


def test_read_settings_for_retrieval_empty_seed():
    from src.tools.setting_context import read_settings_for_retrieval
    from src.tools import file_tools

    # 空种子应等价于直接 bundle（不抛错）
    out = read_settings_for_retrieval("")
    assert isinstance(out, str)
    assert len(out) > 0 or not (file_tools.PROJECT_ROOT / "data").exists()

"""outline_writer：大纲解析逻辑单测（不调用 LLM）。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/outline_writer/scripts"


@pytest.fixture
def go_mod():
    p = str(SCRIPTS)
    if p not in sys.path:
        sys.path.insert(0, p)
    import generate_outlines as go  # noqa: WPS433

    return go


def test_parse_bracketed_ignores_preamble(go_mod):
    raw = """先啰嗦两句。

【方案1】
第一段多行
情节 A。

【方案2】
情节 B 很长很长很长很长很长很长很长很长很长很长很长很长很长很长很长很长。

【方案3】
情节 C。
"""
    blocks = go_mod._parse_outlines_bracketed(raw)
    assert len(blocks) == 3
    assert "情节 A" in blocks[0]
    assert "情节 B" in blocks[1]
    assert "情节 C" in blocks[2]
    assert "先啰嗦" not in blocks[0]


def test_parse_bracketed_multiline_last_block(go_mod):
    raw = """【方案1】
只有一方案
但有多行
正文。"""
    blocks = go_mod._parse_outlines_bracketed(raw)
    assert len(blocks) == 1
    assert "只有一方案" in blocks[0]
    assert "正文。" in blocks[0]


def test_fallback_long_numbered_lines(go_mod):
    raw = """分析与建议
亮点：
1. 这是一条故意写得很长的亮点说明用来测试回退解析器是否能够把它当成大纲条目而不是切碎。重复。重复。重复。重复。

2. 这是第二条同样足够长的说明文字用于测试回退逻辑在只有数字列表时的行为。重复。重复。重复。重复。

3. 第三条长度合格的测试内容，确保第三段也能被识别。重复。重复。重复。重复。
"""
    blocks = go_mod._parse_outlines_fallback(raw, num_options=3)
    assert len(blocks) == 3
    assert all(len(x) > 50 for x in blocks)

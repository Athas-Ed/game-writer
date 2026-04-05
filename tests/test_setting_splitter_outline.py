"""setting-splitter：中文大纲「一、 / （一） / 1．小节」解析。"""

from pathlib import Path
import tempfile

import pytest

from skills.setting_splitter.scripts import run as splitter


_OUTLINE_SAMPLE = """一、核心势力与冲突
（一）审判日组织
1．概述
秘密组织。
2．核心目标
普派。
3．主要手段
挖掘。
4．现状
分裂。
（二）莱茵生命
1．概述
公司。
2．核心目标
宇宙。
3．主要行动
宇航。
4．现状
入驻。
二、关键地点
（一）莱茵园区
1．概述
特里蒙。
2．核心意义
舞台。
3．叙事要点
长居。
4．环境特点
白色。
（二）莱塔尼亚总部
1．概述
城堡。
2．核心意义
内战。
3．叙事要点
基地。
4．环境特点
地下。
三、核心人物
（一）极青
1．基本信息
性别：男
2．性格与动机
内敛。
（二）缪尔赛思
1．基本信息
性别：女
2．性格与动机
活泼。
"""


@pytest.fixture()
def isolated_splitter_project(monkeypatch: pytest.MonkeyPatch):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        monkeypatch.setattr(splitter, "PROJECT_ROOT", root)
        monkeypatch.setattr(
            splitter,
            "_CANONICAL_TYPE_ROOTS",
            frozenset((root / rel).resolve() for rel in set(splitter.TYPE_DIR_MAP.values())),
        )
        yield root


def test_outline_mode_writes_one_file_per_entity(isolated_splitter_project: Path) -> None:
    splitter.run(_OUTLINE_SAMPLE)
    files = sorted(isolated_splitter_project.rglob("*.md"))
    rels = {f.relative_to(isolated_splitter_project).as_posix() for f in files}
    assert len(rels) == 6
    assert "data/背景设定/势力/审判日组织.md" in rels
    assert "data/背景设定/势力/莱茵生命.md" in rels
    assert "data/背景设定/地点/莱茵园区.md" in rels
    assert "data/背景设定/地点/莱塔尼亚总部.md" in rels
    assert "data/角色设定/极青.md" in rels
    assert "data/角色设定/缪尔赛思.md" in rels


def test_strip_duplicate_title_echo_under_heading(isolated_splitter_project: Path) -> None:
    """小节正文首行若与 ### 标题重复（Word 常见），应去掉。"""
    sample = """一、核心势力与冲突
（一）回声测试组织
1．概述
概述
这是正文，不应再出现单独一行「概述」。
2．核心目标
核心目标
目标下的真实内容。
"""
    splitter.run(sample)
    p = isolated_splitter_project / "data" / "背景设定" / "势力" / "回声测试组织.md"
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "### 概述" in text
    assert "这是正文" in text
    # 不应在 ### 概述 下紧跟又一单独行「概述」再接正文（允许句内出现「概述」二字）
    assert "\n\n概述\n\n这是正文" not in text
    assert "### 核心目标" in text
    assert "目标下的真实内容" in text


def test_structural_numbered_lines_do_not_fragment_entity(isolated_splitter_project: Path) -> None:
    """无（一）大纲时，1．概述 + 2．核心目标 仍应保持为单一块（若在同一段落内）。"""
    block = """审判日组织
1．概述
A
2．核心目标
B
"""
    splitter.run(block)
    files = list(isolated_splitter_project.rglob("*.md"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    h2 = [ln for ln in text.splitlines() if ln.startswith("## ") and not ln.startswith("###")]
    assert len(h2) == 1
    assert "### " in text

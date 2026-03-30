"""分块元数据与 SettingsRoute 行为测试（使用临时 data/，不依赖仓库真实设定）。"""

from pathlib import Path

import pytest

from src.tools.data_chunks import (
    chunk_markdown,
    format_chunks_for_file,
    format_routing_index,
    invalidate_data_chunks_cache,
    list_files_in_data_subdir,
    list_md_files_under_data,
)
from src.tools.settings_route import settings_route


@pytest.fixture
def isolated_data(monkeypatch, tmp_path: Path):
    root = tmp_path
    data = root / "data" / "角色设定"
    data.mkdir(parents=True)
    long_body = "详细设定内容。" * 80
    (data / "测试角色.md").write_text(f"## 基础信息\n\n{long_body}\n\n## 性格\n\n{long_body}\n", encoding="utf-8")
    monkeypatch.setattr("src.tools.data_chunks.PROJECT_ROOT", root)
    monkeypatch.setattr("src.tools.data_chunks.DATA_ROOT", root / "data")
    invalidate_data_chunks_cache()
    yield root
    invalidate_data_chunks_cache()


def test_chunk_markdown_heading_level():
    text = "## 标题A\n\n" + "正文。" * 100 + "\n\n### 子标题\n\n" + "子文。" * 100
    chunks = chunk_markdown(text)
    assert len(chunks) >= 1
    assert chunks[0][0] == "标题A"
    assert chunks[0][2] == 2


def test_routing_list_and_chunks(isolated_data):
    idx = format_routing_index(max_files_listed=50)
    assert "角色设定" in idx
    assert "data/角色设定/测试角色.md" in idx

    out = format_chunks_for_file("data/角色设定/测试角色.md", max_total_chars=100_000)
    assert "chunk_ref=data/角色设定/测试角色.md#" in out
    assert "data_category=角色设定" in out
    assert "基础信息" in out


def test_list_files_in_subdir(isolated_data):
    s = list_files_in_data_subdir("角色设定")
    assert "测试角色.md" in s


def test_settings_route_subcommands(isolated_data):
    assert "角色设定" in settings_route("list")
    assert "测试角色.md" in settings_route("files dir=角色设定")
    assert "chunk_ref=" in settings_route("chunks path=data/角色设定/测试角色.md")
    assert "SearchDocs" in settings_route("search 测试角色") or "分数=" in settings_route("search 测试角色")


def test_list_md_files_under_data(isolated_data):
    files = list_md_files_under_data()
    assert any("测试角色.md" in f for f in files)


def test_gather_evidence_context(isolated_data):
    from src.tools.search_docs import gather_evidence_context

    ctx = gather_evidence_context("测试角色 基础信息", top_k=6, max_total_chars=100_000)
    assert "data/角色设定/测试角色.md" in ctx
    assert "基础信息" in ctx

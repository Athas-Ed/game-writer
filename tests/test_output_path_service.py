from pathlib import Path

import pytest

from src.services.output_path_service import OutputTargetsCache, load_output_targets, normalize_write_path


def test_normalize_rejects_absolute_and_traversal(tmp_path: Path):
    cache = OutputTargetsCache(mapping={"角色设定": "data/角色设定"}, mtime=None)
    with pytest.raises(ValueError):
        normalize_write_path("C:/Windows/a.txt", cache)
    with pytest.raises(ValueError):
        normalize_write_path("../x.txt", cache)
    with pytest.raises(ValueError):
        normalize_write_path("data/../x.txt", cache)


def test_normalize_maps_spoken_head_to_data_dir():
    cache = OutputTargetsCache(mapping={"剧情大纲": "data/剧情大纲"}, mtime=None)
    assert normalize_write_path("剧情大纲/abc.md", cache) == "data/剧情大纲/abc.md"
    assert normalize_write_path("剧情大纲", cache) == "data/剧情大纲"


def test_load_output_targets_fallback_when_missing(tmp_path: Path):
    p = tmp_path / "output_targets.json"
    cache = load_output_targets(p)
    assert "角色设定" in cache.mapping


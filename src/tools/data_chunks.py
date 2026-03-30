"""
data/ 下 Markdown 的分块与元数据索引，供 SearchDocs、SettingsRoute 等复用。

元数据包含：路径、文件名、data 下一级分类、标题层级、块序号等，便于结构化路由与截断读取。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_ROOT = PROJECT_ROOT / "data"

_SUPPORTED_EXTS = {".md"}


def _norm_project_rel_path(p: str) -> str:
    """与 file_tools._norm_rel_path 一致，避免 data_chunks 反向依赖 file_tools。"""
    path = (p or "").strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise ValueError("不允许读取绝对路径。请使用相对路径（例如 data/角色设定/xxx.md）。")
    if ".." in path.split("/"):
        raise ValueError("不允许使用 '..' 路径穿越。")
    return path


_DATA_MTIME: Optional[float] = None
_CHUNKS_CACHE: Optional[List["ChunkRecord"]] = None
_FILE_TOKEN_INDEX: Optional[Dict[str, Set[str]]] = None


@dataclass(frozen=True)
class ChunkRecord:
    """单个 Markdown 语义块（通常对应一个 ## 标题下全文或一个无标题段落合并块）。"""

    rel_path: str
    """相对项目根，如 data/角色设定/林夕.md"""

    stem: str
    """不含扩展名的文件名"""

    data_category: str
    """data/ 下第一级目录名；若在 data 根下则为 (root)"""

    data_rel: str
    """相对 data/ 的路径 posix，如 角色设定/林夕.md"""

    chunk_index: int
    """同一文件内从 0 递增"""

    heading: str
    """展示用标题文本（无标题块为「段落块」）"""

    heading_level: int
    """1–6 为 ATX 标题级别；0 表示段落合并块"""

    text: str
    norm_text: str
    tokens: Tuple[str, ...]

    @property
    def chunk_ref(self) -> str:
        return f"{self.rel_path}#{self.chunk_index}"


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""


def _normalize(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[\s\-_·。。，、；;:：!?！？()\[\]{}\"'“”]+", "", s)
    return s


def _tokenize(s: str) -> List[str]:
    s = s or ""
    return re.findall(r"[\u4e00-\u9fffA-Za-z0-9_]+", s)


def chunk_markdown(text: str, *, min_chars: int = 120) -> List[Tuple[str, str, int]]:
    """
    按标题切片；无标题时按段落合并为块。
    返回 [(heading, chunk_text, heading_level), ...]，heading_level 0 表示段落块。
    """
    heading_pat = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
    matches = list(heading_pat.finditer(text or ""))

    chunks: List[Tuple[str, str, int]] = []
    if matches:
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            level = len(m.group(1))
            heading_text = m.group(2).strip()
            chunk_text = text[start:end].strip()
            if len(chunk_text) >= min_chars:
                chunks.append((heading_text, chunk_text, level))
        return chunks

    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    buf: List[str] = []
    cur_len = 0
    for p in paras:
        if cur_len + len(p) > 1200 and buf:
            combined = "\n\n".join(buf).strip()
            if len(combined) >= min_chars:
                chunks.append(("段落块", combined, 0))
            buf = [p]
            cur_len = len(p)
        else:
            buf.append(p)
            cur_len += len(p)
    if buf:
        combined = "\n\n".join(buf).strip()
        if len(combined) >= min_chars:
            chunks.append(("段落块", combined, 0))
    return chunks


def _path_metadata(rel_path: str) -> Tuple[str, str, str]:
    """返回 (stem, data_category, data_rel posix)。"""
    p = Path(rel_path)
    stem = p.stem
    try:
        rel_to_data = Path(rel_path).relative_to("data")
    except ValueError:
        return stem, "(root)", rel_path
    parts = rel_to_data.parts
    category = parts[0] if parts else "(root)"
    data_rel = rel_to_data.as_posix()
    return stem, category, data_rel


def _build_chunk_records() -> Tuple[List[ChunkRecord], Dict[str, Set[str]]]:
    records: List[ChunkRecord] = []
    file_token_index: Dict[str, Set[str]] = {}

    if not DATA_ROOT.exists() or not DATA_ROOT.is_dir():
        return records, file_token_index

    for path in sorted(DATA_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _SUPPORTED_EXTS:
            continue
        rel_path = path.relative_to(PROJECT_ROOT).as_posix()
        text = _safe_read_text(path)
        if not text.strip():
            continue

        stem, category, data_rel = _path_metadata(rel_path)
        for tok in set(_tokenize(rel_path)):
            file_token_index.setdefault(tok, set()).add(rel_path)

        for idx, (heading, chunk_text, level) in enumerate(chunk_markdown(text)):
            toks = tuple(_tokenize(chunk_text))
            if not toks:
                continue
            records.append(
                ChunkRecord(
                    rel_path=rel_path,
                    stem=stem,
                    data_category=category,
                    data_rel=data_rel,
                    chunk_index=idx,
                    heading=heading,
                    heading_level=level,
                    text=chunk_text,
                    norm_text=_normalize(chunk_text),
                    tokens=toks,
                )
            )
    return records, file_token_index


def invalidate_data_chunks_cache() -> None:
    """测试或外部批量改写 data/ 后可调用，强制下次重建索引。"""
    global _DATA_MTIME, _CHUNKS_CACHE, _FILE_TOKEN_INDEX
    _DATA_MTIME = None
    _CHUNKS_CACHE = None
    _FILE_TOKEN_INDEX = None


def get_data_chunks_index() -> Tuple[List[ChunkRecord], Dict[str, Set[str]]]:
    """返回 (全部 ChunkRecord, 路径 token -> 文件集合)。按 data/ 目录 mtime 做轻量缓存。"""
    global _DATA_MTIME, _CHUNKS_CACHE, _FILE_TOKEN_INDEX
    try:
        current_mtime = DATA_ROOT.stat().st_mtime
    except Exception:
        current_mtime = None

    if _CHUNKS_CACHE is not None and _DATA_MTIME == current_mtime and _FILE_TOKEN_INDEX is not None:
        return _CHUNKS_CACHE, _FILE_TOKEN_INDEX

    _DATA_MTIME = current_mtime
    records, ft = _build_chunk_records()
    _CHUNKS_CACHE = records
    _FILE_TOKEN_INDEX = ft
    return records, ft


def list_md_files_under_data() -> List[str]:
    """所有 data 下 .md 的相对项目根路径，已排序。"""
    if not DATA_ROOT.exists():
        return []
    out: List[str] = []
    for path in sorted(DATA_ROOT.rglob("*.md")):
        if path.is_file():
            out.append(path.relative_to(PROJECT_ROOT).as_posix())
    return out


def format_routing_index(*, max_files_listed: int = 200) -> str:
    """
    结构化路由表：按 data 下一级目录分组列出 .md 路径，供 Agent 先选文件再 ReadFile / chunks。
    """
    files = list_md_files_under_data()
    if not files:
        return "SettingsRoute：data/ 下未找到 .md 文件。"

    by_cat: Dict[str, List[str]] = {}
    for rel in files:
        _, cat, _ = _path_metadata(rel)
        by_cat.setdefault(cat, []).append(rel)

    lines: List[str] = [
        "【设定库路由索引】按 data 下一级目录分组（用于先缩小范围再读文件）。",
        f"共 {len(files)} 个 Markdown 文件。",
        "",
    ]
    listed = 0
    for cat in sorted(by_cat.keys()):
        group = sorted(by_cat[cat])
        lines.append(f"## {cat}（{len(group)}）")
        for rel in group:
            if listed >= max_files_listed:
                rest_count = len(files) - listed
                lines.append(f"- … 未列出其余 {rest_count} 个文件（请用 `files dir=…` 或 `search`）。")
                return "\n".join(lines)
            lines.append(f"- {rel}")
            listed += 1
        lines.append("")

    lines.append("下一步：用 `SettingsRoute` 输入 `chunks path=data/...` 查看分块元数据；或 `search …` 关键词检索。")
    return "\n".join(lines).strip()


def list_files_in_data_subdir(dir_name: str) -> str:
    """列出 data/<dir_name>/ 下（递归）所有 .md。"""
    name = (dir_name or "").strip().strip("/").replace("\\", "/")
    if not name or ".." in name.split("/"):
        return "SettingsRoute：dir 参数无效。"

    base = DATA_ROOT / name
    if not base.exists():
        return f"SettingsRoute：目录不存在 data/{name}"
    if not base.is_dir():
        return f"SettingsRoute：不是目录 data/{name}"

    paths = sorted(p.relative_to(PROJECT_ROOT).as_posix() for p in base.rglob("*.md") if p.is_file())
    if not paths:
        return f"SettingsRoute：data/{name} 下无 .md 文件。"

    lines = [f"data/{name} 下共 {len(paths)} 个 .md：", ""]
    lines.extend(f"- {p}" for p in paths)
    return "\n".join(lines)


def format_chunks_for_file(rel_path: str, *, max_total_chars: int = 28_000) -> str:
    """返回某文件的全部分块及元数据，总字符上限防止撑爆上下文。"""
    try:
        rp = _norm_project_rel_path(rel_path)
    except Exception as e:
        return f"SettingsRoute：路径无效：{e}"

    if not rp.lower().endswith(".md"):
        return "SettingsRoute：chunks 仅支持 .md 文件路径。"

    full = PROJECT_ROOT / rp
    if not full.is_file():
        return f"SettingsRoute：文件不存在：{rp}"

    records, _ = get_data_chunks_index()
    mine = [c for c in records if c.rel_path == rp]
    if not mine:
        # 文件存在但无有效块（过短或空）
        text = _safe_read_text(full)
        if not text.strip():
            return f"SettingsRoute：{rp} 为空或无法读取。"
        return (
            f"SettingsRoute：{rp} 未产生分块（内容可能过短）。请直接用 ReadFile 读取全文。\n"
            f"预览：{text[:800]}…"
            if len(text) > 800
            else f"全文：\n{text}"
        )

    lines: List[str] = [
        f"【分块+元数据】{rp}（共 {len(mine)} 块）",
        "",
    ]
    used = 0
    for c in mine:
        header = (
            f"### chunk_ref={c.chunk_ref}\n"
            f"- data_category={c.data_category}\n"
            f"- heading_level={c.heading_level}\n"
            f"- heading={c.heading}\n"
            f"- char_count={len(c.text)}\n"
            "正文：\n"
        )
        block = header + c.text
        if used + len(block) > max_total_chars:
            lines.append(f"… 已截断（剩余块未展示）。请缩小范围或用 SearchDocs 精确定位。")
            break
        lines.append(block)
        lines.append("")
        used += len(block)

    lines.append("建议：需要改文件时用 ReadFile 读全文；检索跨文件用 SearchDocs。")
    return "\n".join(lines).strip()

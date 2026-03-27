from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

def _detect_project_root(start: Path) -> Path:
    """
    兼容不同加载方式：从当前脚本目录向上寻找项目根目录。
    以存在 `pyproject.toml` 作为最可靠信号；其次匹配 `src/` + `skills/`。
    """
    for p in [start, *start.parents]:
        if (p / "pyproject.toml").exists():
            return p
        if (p / "src").exists() and (p / "skills").exists():
            return p
    # 兜底：保持旧逻辑（scripts -> skill -> skills -> project_root）
    return start.parents[3]


# 兼容不同加载方式：确保可 import src.*
PROJECT_ROOT = _detect_project_root(SCRIPT_DIR)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass(frozen=True)
class Entry:
    type_name: str
    name: str
    raw_block: str
    collection: str | None = None  # 章节/集合标题（用于子目录）


TYPE_DIR_MAP: dict[str, str] = {
    "人物": "data/角色设定",
    "角色": "data/角色设定",
    "种族": "data/背景设定/种族",
    "阵营": "data/背景设定/阵营",
    "地图": "data/背景设定/地图",
    "历史": "data/背景设定/历史",
    "未分类": "data/背景设定/未分类",
}

TYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("人物", ["人物", "角色", "角色设定"]),
    ("种族", ["种族"]),
    ("阵营", ["阵营", "势力"]),
    ("地图", ["地图", "地点", "区域"]),
    ("历史", ["历史", "纪年", "大事记"]),
]

_NUMBERED_ITEM_RE = re.compile(r"^(?P<num>\d{1,3})\s*[．\.\、]\s*(?P<title>.+?)\s*$")
_CN_SECTION_RE = re.compile(r"^（(?P<num>\d{1,3})）\s*(?P<title>.+?)\s*$")
_COLLECTION_RE = re.compile(r"^（[^）]{1,8}）\s*(?P<title>.+?)\s*$")


def _split_blocks(text: str) -> list[str]:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    blocks = [b.strip() for b in re.split(r"\n{2,}", normalized) if b.strip()]
    return blocks


def _split_numbered_items(block: str) -> list[str]:
    """
    处理“同一段里包含多个原子条目”的场景：
    例如“关键地点”下的
    1．xxx ... 2．yyy ...
    将其拆为多个独立块，便于各自生成 md 文件。
    """
    lines = [ln.rstrip() for ln in block.replace("\r\n", "\n").replace("\r", "\n").splitlines()]
    indices: list[int] = []
    for i, ln in enumerate(lines):
        if _NUMBERED_ITEM_RE.match(ln.strip()):
            indices.append(i)
    if len(indices) < 2:
        return [block]

    # 尝试提取集合/章节标题（出现在第一条编号项之前）
    header_lines = [ln.strip() for ln in lines[: indices[0]] if ln.strip()]
    collection: str | None = None
    if header_lines:
        # 取最后一行更稳（常见：前面还有“（二）关键地点”这种标题）
        cand = header_lines[-1]
        m = _COLLECTION_RE.match(cand)
        collection = (m.group("title").strip() if m else cand).strip() or None

    chunks: list[str] = []
    for j, start in enumerate(indices):
        end = indices[j + 1] if j + 1 < len(indices) else len(lines)
        chunk_lines = lines[start:end]
        chunk = "\n".join([c for c in chunk_lines if c.strip()]).strip()
        if collection:
            chunk = f"【集合】{collection}\n{chunk}"
        if chunk:
            chunks.append(chunk)
    return chunks or [block]


def _first_nonempty_line(block: str) -> str:
    for line in block.splitlines():
        s = line.strip()
        if s:
            return s
    return ""


def _extract_title_line(block: str) -> str | None:
    first = _first_nonempty_line(block)
    if not first:
        return None
    if first.startswith("##"):
        return first
    if "：" in first:
        for key, _ in TYPE_KEYWORDS:
            if first.startswith(f"{key}：") or first.startswith(f"{key}:"):
                return first
    return None


def _detect_type_from_text(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "未分类"
    lowered = t.lower()
    for canonical, keys in TYPE_KEYWORDS:
        for k in keys:
            if k in t or k.lower() in lowered:
                return canonical
    return "未分类"


_TITLE_RE = re.compile(r"^(?P<hashes>#{2,6})\s*(?P<title>.+?)\s*$")
_PREFIXED_RE = re.compile(r"^(?P<type>[^：:]{1,8})[：:]\s*(?P<name>.+?)\s*$")


def _parse_entry(block: str) -> Entry:
    collection: str | None = None
    blk = block
    # 兼容 _split_numbered_items 注入的集合标记
    if blk.startswith("【集合】"):
        first_line = _first_nonempty_line(blk)
        if first_line.startswith("【集合】"):
            collection = first_line.replace("【集合】", "", 1).strip() or None
            blk = "\n".join(blk.splitlines()[1:]).strip()

    title_line = _extract_title_line(block)
    if not title_line:
        first = _first_nonempty_line(blk)
        # 支持“1．条目名”这种原子条目标题
        m = _NUMBERED_ITEM_RE.match(first)
        if m:
            name = m.group("title").strip() or "未命名"
            # 这类条目通常来自“地点/地图”类集合文本，默认按全文关键词推断
            type_name = _detect_type_from_text(blk)
        else:
            type_name = _detect_type_from_text(first)
            name = first[:30].strip() or "未命名"
        return Entry(type_name=type_name, name=name, raw_block=blk, collection=collection)

    m = _TITLE_RE.match(title_line)
    title_text = m.group("title") if m else title_line.lstrip("#").strip()

    pm = _PREFIXED_RE.match(title_text)
    if pm:
        type_guess = _detect_type_from_text(pm.group("type"))
        name = pm.group("name").strip()
        return Entry(type_name=type_guess, name=name or "未命名", raw_block=blk, collection=collection)

    type_guess = _detect_type_from_text(title_text)
    return Entry(type_name=type_guess, name=title_text or "未命名", raw_block=blk, collection=collection)


def _sanitize_filename(name: str) -> str:
    n = (name or "").strip()
    n = re.sub(r"[\\/:*?\"<>|]+", " ", n)  # Windows illegal chars
    n = re.sub(r"\s+", " ", n).strip(" .")
    if not n:
        n = "未命名"
    if len(n) > 80:
        n = n[:80].rstrip()
    return n


def _sanitize_dirname(name: str) -> str:
    # 与文件名类似，但更保守一点
    return _sanitize_filename(name)


def _parse_kv_lines(lines: Iterable[str]) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        s2 = s[1:].strip() if s.startswith(("-", "*")) else s
        if "：" in s2:
            k, v = s2.split("：", 1)
        elif ":" in s2:
            k, v = s2.split(":", 1)
        else:
            continue
        k = k.strip()
        v = v.strip()
        if not k or not v:
            continue
        items.append((k, v))
    return items


def _format_structured_sections(lines: list[str]) -> list[tuple[str, str]] | None:
    """
    处理形如：
    （1）概述
    xxxx
    （2）核心意义
    yyyy
    （3）叙事要点
    a
    b
    的结构化段落。
    """
    items: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        m = _CN_SECTION_RE.match(ln)
        if not m:
            i += 1
            continue
        title = m.group("title").strip()
        i += 1
        buf: list[str] = []
        while i < len(lines):
            nxt = lines[i].strip()
            if _CN_SECTION_RE.match(nxt):
                break
            if nxt:
                # 统一常见项目符号
                if nxt.startswith(""):
                    buf.append("- " + nxt.lstrip("").strip())
                else:
                    buf.append(nxt)
            i += 1
        value = "\n".join(buf).strip()
        if title and value:
            items.append((title, value))
    return items or None


def _format_markdown(entry: Entry) -> str:
    block = entry.raw_block.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [ln.rstrip() for ln in block.splitlines()]

    if lines:
        first = lines[0].strip()
        if first.startswith("##"):
            lines = lines[1:]

    # 去掉“1．条目名”行（如果存在），避免重复出现在正文里
    if lines:
        first2 = lines[0].strip()
        if _NUMBERED_ITEM_RE.match(first2):
            lines = lines[1:]

    structured = _format_structured_sections(lines)
    kvs = structured if structured is not None else _parse_kv_lines(lines)
    rest_text_lines = [
        ln
        for ln in lines
        if ln.strip()
        and ln.strip().lstrip("-*").strip()
        and ("：" not in ln and ":" not in ln)
    ]

    out: list[str] = [f"## {entry.name}"]
    if kvs:
        for k, v in kvs:
            if "\n" in v and v.lstrip().startswith("- "):
                out.append(f"- **{k}**：")
                out.extend([f"  {ln}" for ln in v.splitlines()])
            else:
                out.append(f"- **{k}**：{v}")
    if rest_text_lines:
        out.append("")
        out.extend(rest_text_lines)

    out.append("")
    return "\n".join(out)


def _resolve_output_dir(type_name: str) -> Path:
    rel = TYPE_DIR_MAP.get(type_name, TYPE_DIR_MAP["未分类"])
    return PROJECT_ROOT / rel


def _write_entry(entry: Entry) -> Path:
    out_dir = _resolve_output_dir(entry.type_name)
    if entry.collection:
        out_dir = out_dir / _sanitize_dirname(entry.collection)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(entry.name) + ".md"
    path = out_dir / filename
    content = _format_markdown(entry)
    path.write_text(content, encoding="utf-8")
    if not path.exists():
        raise RuntimeError(f"写入失败：目标文件未落盘：{path}")
    return path


def run(input_text: str) -> str:
    """
    统一技能入口：接收用户输入并返回可展示文本。
    输入通常为一份长文本设定（txt/md内容）。
    """
    raw = (input_text or "").strip()
    if not raw:
        return "setting-splitter 输入为空，请粘贴或提供设定长文本内容。"

    # 兼容：若用户输入的是本地文件路径，则读取文件内容
    candidate = raw.strip().strip('"').strip("'")
    p = Path(candidate)
    if p.exists() and p.is_file() and p.suffix.lower() in {".txt", ".md"}:
        text = p.read_text(encoding="utf-8")
    else:
        text = raw

    blocks = _split_blocks(text)
    if not blocks:
        return "setting-splitter 未发现可处理的段落块（请确保段落之间用空行分隔）。"

    expanded: list[str] = []
    for b in blocks:
        # 第二阶段拆分：对单块内部的“1．/2．”原子条目做进一步拆分
        expanded.extend(_split_numbered_items(b))

    entries = [_parse_entry(b) for b in expanded]
    written: list[Path] = []
    for e in entries:
        written.append(_write_entry(e))

    lines = [f"已执行技能 setting-splitter，共拆分并写入 {len(written)} 个文件："]
    for p in written:
        try:
            rel = p.relative_to(PROJECT_ROOT)
            lines.append(f"- {rel.as_posix()}")
        except Exception:
            lines.append(f"- {str(p)}")
    return "\n".join(lines)


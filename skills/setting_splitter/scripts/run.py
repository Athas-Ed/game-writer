from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

# 兼容不同加载方式：确保可 import src.*（项目根目录在 skills/ 的上一级）
PROJECT_ROOT = SCRIPT_DIR.parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass(frozen=True)
class Entry:
    type_name: str
    name: str
    raw_block: str


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


def _split_blocks(text: str) -> list[str]:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    blocks = [b.strip() for b in re.split(r"\n{2,}", normalized) if b.strip()]
    return blocks


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
    title_line = _extract_title_line(block)
    if not title_line:
        first = _first_nonempty_line(block)
        type_name = _detect_type_from_text(first)
        name = first[:30].strip() or "未命名"
        return Entry(type_name=type_name, name=name, raw_block=block)

    m = _TITLE_RE.match(title_line)
    title_text = m.group("title") if m else title_line.lstrip("#").strip()

    pm = _PREFIXED_RE.match(title_text)
    if pm:
        type_guess = _detect_type_from_text(pm.group("type"))
        name = pm.group("name").strip()
        return Entry(type_name=type_guess, name=name or "未命名", raw_block=block)

    type_guess = _detect_type_from_text(title_text)
    return Entry(type_name=type_guess, name=title_text or "未命名", raw_block=block)


def _sanitize_filename(name: str) -> str:
    n = (name or "").strip()
    n = re.sub(r"[\\/:*?\"<>|]+", " ", n)  # Windows illegal chars
    n = re.sub(r"\s+", " ", n).strip(" .")
    if not n:
        n = "未命名"
    if len(n) > 80:
        n = n[:80].rstrip()
    return n


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


def _format_markdown(entry: Entry) -> str:
    block = entry.raw_block.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [ln.rstrip() for ln in block.splitlines()]

    if lines:
        first = lines[0].strip()
        if first.startswith("##"):
            lines = lines[1:]

    kvs = _parse_kv_lines(lines)
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
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(entry.name) + ".md"
    path = out_dir / filename
    content = _format_markdown(entry)
    path.write_text(content, encoding="utf-8")
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

    entries = [_parse_entry(b) for b in blocks]
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


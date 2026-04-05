from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import re
import sys
import unicodedata
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
    collection: str | None = None  # 章节/集合标题（仅作解析上下文，不生成子目录）


TYPE_DIR_MAP: dict[str, str] = {
    "人物": "data/角色设定",
    "角色": "data/角色设定",
    "种族": "data/背景设定/种族",
    "势力": "data/背景设定/势力",
    "地点": "data/背景设定/地点",
    "历史": "data/背景设定/历史",
    "未分类": "data/背景设定/未分类",
}

TYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("人物", ["人物", "角色", "角色设定"]),
    ("种族", ["种族"]),
    ("势力", ["势力", "阵营", "派系"]),
    ("地点", ["地点", "地图", "区域", "位置"]),
    ("历史", ["历史", "纪年", "大事记"]),
]

# 技能写入唯一允许落点的根目录（用于空目录清理白名单，避免误删 data/ 其他内容）
_CANONICAL_TYPE_ROOTS: frozenset[Path] = frozenset(
    (PROJECT_ROOT / rel).resolve() for rel in set(TYPE_DIR_MAP.values())
)

_NUMBERED_ITEM_RE = re.compile(r"^(?P<num>\d{1,3})\s*[．\.\、]\s*(?P<title>.+?)\s*$")
_CN_SECTION_RE = re.compile(r"^（(?P<num>\d{1,3})）\s*(?P<title>.+?)\s*$")
# Word 常见「（一）概述」；数字与中文序号均允许
_CN_SECTION_ANY_RE = re.compile(r"^（(?P<num>[0-9一二三四五六七八九十百千两]+)）\s*(?P<title>.+?)\s*$")
_COLLECTION_RE = re.compile(r"^（[^）]{1,8}）\s*(?P<title>.+?)\s*$")

# 「1．概述」「2．核心目标」等为条目内小节标题，不是独立实体；遇此类编号行禁止按原子条目拆分
_STRUCTURE_SUBSECTION_TITLES: frozenset[str] = frozenset(
    {
        "概述",
        "核心目标",
        "主要手段",
        "主要行动",
        "现状",
        "核心意义",
        "叙事要点",
        "环境特点",
        "基本信息",
        "性格与动机",
        "能力与技能",
        "关键关系",
        "背景与经历",
        "主题与象征",
        "来历",
        "经历摘要",
        "核心动机",
        "价值观与信仰",
        "情感倾向",
        "深层意识",
        "特殊权限",
        "专业技能",
        "战斗特长",
        "非战斗特长",
        "特殊能力",
        "盟友关系",
        "敌对关系",
        "核心关系",
        "阵营定位",
        "别名",
        "性别",
        "种族",
        "阵营",
        "身份",
        "外貌特征",
        "着装习惯",
        "声线",
        "语气特点",
        "声线/语气特点",
    }
)

_TOP_OUTLINE_SECTION_RE = re.compile(r"^([一二三四五六七八九十]+)、\s*(.+)$")
_MINOR_ENTITY_HEAD_RE = re.compile(r"^（[一二三四五六七八九十\d]{1,3}）\s*(.+)$")


def _normalize_unicode_text(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "").replace("\r\n", "\n").replace("\r", "\n"))


def _bulletize_pasted_line(line: str) -> str:
    """Word 粘贴：制表符/特殊空白、项目符号 → 规范 Markdown 列表行。"""
    raw = line.rstrip()
    if not raw.strip():
        return ""
    t = unicodedata.normalize("NFKC", raw.strip())
    t = re.sub(r"[\t\u00a0\u2007\u202f\ufeff]+", " ", t)
    for prefix in (
        "\uf06c",
        "\uf06e",
        "\uf0a7",
        "\uf0b7",
        "",
        "•",
        "·",
        "●",
        "○",
        "◎",
        "□",
        "■",
        "◆",
        "◇",
        "※",
    ):
        if t.startswith(prefix):
            rest = t[len(prefix) :].lstrip()
            return "- " + rest if rest else "-"
    if t.startswith(("- ", "* ")):
        return t
    return t


def _line_section_header_title(line: str) -> str | None:
    """识别小节标题行：`1．概述` 或 `（1）概述` / `（一）概述`。"""
    s = line.strip()
    if not s:
        return None
    m = _NUMBERED_ITEM_RE.match(s)
    if m:
        return (m.group("title") or "").strip() or None
    m = _CN_SECTION_ANY_RE.match(s)
    if m:
        return (m.group("title") or "").strip() or None
    return None


def _strip_leading_title_echo(text: str, title: str) -> str:
    """
    去掉正文开头与给定标题重复的一行或多行（跳过中间空行）。
    常见于 Word 粘贴：在章节标题下再单独占一行重复同一词。
    不删除「标题：值」整行，仅删除与标题完全相同的单行。
    """
    if not (text and title):
        return (text or "").strip()
    h = unicodedata.normalize("NFKC", title.strip())
    if not h:
        return text.strip()
    lines = text.split("\n")
    idx = 0
    while idx < len(lines):
        raw = lines[idx]
        if not raw.strip():
            idx += 1
            continue
        n = unicodedata.normalize("NFKC", raw.strip())
        if n == h:
            idx += 1
            continue
        if n in (f"《{h}》", f"「{h}」", f"【{h}】", f"**{h}**"):
            idx += 1
            continue
        break
    return "\n".join(lines[idx:]).strip()


def _trim_redundant_preamble(preamble: str, entry_name: str) -> str:
    """去掉序言中与条目名重复的领头行。"""
    return _strip_leading_title_echo((preamble or "").strip(), entry_name or "")


def _split_preamble_and_subsections(lines: list[str]) -> tuple[str, list[tuple[str, str]]]:
    n = len(lines)
    i = 0
    preamble_raw: list[str] = []
    while i < n:
        if _line_section_header_title(lines[i]) is not None:
            break
        preamble_raw.append(lines[i])
        i += 1
    pre_parts: list[str] = []
    for ln in preamble_raw:
        if ln.strip():
            pre_parts.append(_bulletize_pasted_line(ln))
    preamble = "\n".join(pre_parts).strip()
    preamble = re.sub(r"\n{3,}", "\n\n", preamble)

    items: list[tuple[str, str]] = []
    while i < n:
        title = _line_section_header_title(lines[i])
        if not title:
            i += 1
            continue
        i += 1
        buf: list[str] = []
        while i < n:
            if _line_section_header_title(lines[i]) is not None:
                break
            s = lines[i]
            if s.strip():
                buf.append(_bulletize_pasted_line(s))
            else:
                buf.append("")
            i += 1
        val = "\n".join(buf).strip()
        val = re.sub(r"\n{3,}", "\n\n", val)
        if title and val:
            items.append((title, val))
    return preamble, items


def _refine_plain_lines_to_kv_bullets(value: str) -> str:
    """将「键：值」独立行转为 `- **键**：值`，保留已有列表与长段落。"""
    lines = value.split("\n")
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            out.append("")
            continue
        if s.startswith("- ") or s.startswith("* "):
            out.append(s)
            continue
        if "：" in s and not s.startswith("#"):
            k, _, rest = s.partition("：")
            k = k.strip()
            rest = rest.strip()
            if 1 <= len(k) <= 32 and rest:
                out.append(f"- **{k}**：{rest}")
                continue
        if ":" in s and "：" not in s and not s.startswith("#"):
            k, _, rest = s.partition(":")
            k = k.strip()
            rest = rest.strip()
            if 1 <= len(k) <= 32 and rest and k.isascii():
                out.append(f"- **{k}**：{rest}")
                continue
        out.append(s)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


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

    titles: list[str] = []
    for i in indices:
        m = _NUMBERED_ITEM_RE.match(lines[i].strip())
        if m:
            titles.append(m.group("title").strip())
    if titles and all(t in _STRUCTURE_SUBSECTION_TITLES for t in titles):
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


def _normalize_type_name(type_name: str) -> str:
    """兼容旧技能文档中的「阵营/地图」叫法，统一为资料库目录用语。"""
    m = {"阵营": "势力", "地图": "地点"}
    return m.get(type_name, type_name)


def _infer_type_from_first_line(name: str) -> str | None:
    """单行标题为实体名时的后缀启发（避免在全文中匹配「组织」等泛词）。"""
    n = (name or "").strip()
    if not n or len(n) > 48:
        return None
    if n.endswith(("组织", "公司", "联盟", "军团", "教会", "财团", "集团")):
        return "势力"
    if n.endswith(("园区", "总部", "基地", "城堡", "山谷", "城市", "市镇")):
        return "地点"
    return None


def _infer_type_from_structure(block: str) -> str | None:
    """
    根据常见设定小节推断类型（优先于「未分类」）。
    注意顺序：先人物，再地点，再势力，避免公司/地点类条目误判。
    """
    b = (block or "").strip()
    if not b:
        return None
    if any(x in b for x in ("性别", "外貌特征", "角色主题", "声线/语气", "声线", "语气特点")):
        return "人物"
    if ("环境特点" in b or "核心意义" in b) and "叙事要点" in b:
        return "地点"
    if "核心目标" in b and ("主要手段" in b or "主要行动" in b or "现状" in b):
        return "势力"
    return None


def _map_top_section_to_type(tail: str) -> str | None:
    """「一、核心势力与冲突」「二、关键地点」等大节 → 势力 / 地点 / 人物。"""
    t = (tail or "").strip()
    if not t:
        return None
    if "人物" in t:
        return "人物"
    if "地点" in t:
        return "地点"
    if "势力" in t or "冲突" in t:
        return "势力"
    return None


def _split_outline_entities(text: str) -> list[tuple[str, str | None]]:
    """
    按「（一）实体名」切分为独立块，并结合上一段「一、…」大节推断类型。
    若无此类行则返回空列表，交由旧逻辑处理。
    """
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    section_type: str | None = None
    current: list[str] = []
    active_hint: str | None = None
    out: list[tuple[str, str | None]] = []

    def flush() -> None:
        nonlocal current, active_hint
        if not current:
            return
        block = "\n".join(current).strip()
        if block:
            out.append((block, active_hint))
        current = []
        active_hint = None

    found_minor = False
    for line in raw_lines:
        s = line.strip()
        if not s:
            if current:
                current.append(line)
            continue
        m_top = _TOP_OUTLINE_SECTION_RE.match(s)
        if m_top:
            flush()
            section_type = _map_top_section_to_type(m_top.group(2))
            continue
        m_sub = _MINOR_ENTITY_HEAD_RE.match(s)
        if m_sub:
            found_minor = True
            flush()
            current = [line]
            active_hint = section_type
            continue
        current.append(line)
    flush()
    return out if found_minor else []


def _finalize_entry_type(type_name: str, name: str, raw_block: str) -> str:
    t = _normalize_type_name(type_name)
    if t == "未分类":
        inferred = _infer_type_from_structure(raw_block)
        if inferred:
            t = inferred
    if t == "未分类":
        fl = _infer_type_from_first_line(name)
        if fl:
            t = fl
    return _normalize_type_name(t)


_TITLE_RE = re.compile(r"^(?P<hashes>#{2,6})\s*(?P<title>.+?)\s*$")
_PREFIXED_RE = re.compile(r"^(?P<type>[^：:]{1,8})[：:]\s*(?P<name>.+?)\s*$")


def _parse_entry(block: str, *, type_hint: str | None = None) -> Entry:
    collection: str | None = None
    blk = block
    # 兼容 _split_numbered_items 注入的集合标记
    if blk.startswith("【集合】"):
        first_line = _first_nonempty_line(blk)
        if first_line.startswith("【集合】"):
            collection = first_line.replace("【集合】", "", 1).strip() or None
            blk = "\n".join(blk.splitlines()[1:]).strip()

    first0 = _first_nonempty_line(blk)
    m_ent = _MINOR_ENTITY_HEAD_RE.match(first0.strip()) if first0 else None
    if m_ent:
        name = (m_ent.group(1) or "").strip() or "未命名"
        hint_norm = _normalize_type_name(type_hint) if type_hint else None
        if hint_norm and hint_norm in TYPE_DIR_MAP:
            tname = hint_norm
        else:
            tname = _finalize_entry_type(_detect_type_from_text(name), name, blk)
        e = Entry(type_name=tname, name=name, raw_block=blk, collection=collection)
        return replace(e, type_name=_normalize_type_name(e.type_name))

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
        e = Entry(type_name=type_name, name=name, raw_block=blk, collection=collection)
        return replace(e, type_name=_finalize_entry_type(e.type_name, e.name, e.raw_block))

    m = _TITLE_RE.match(title_line)
    title_text = m.group("title") if m else title_line.lstrip("#").strip()

    pm = _PREFIXED_RE.match(title_text)
    if pm:
        type_guess = _detect_type_from_text(pm.group("type"))
        name = pm.group("name").strip()
        e = Entry(type_name=type_guess, name=name or "未命名", raw_block=blk, collection=collection)
        return replace(e, type_name=_finalize_entry_type(e.type_name, e.name, e.raw_block))

    type_guess = _detect_type_from_text(title_text)
    e = Entry(type_name=type_guess, name=title_text or "未命名", raw_block=blk, collection=collection)
    return replace(e, type_name=_finalize_entry_type(e.type_name, e.name, e.raw_block))


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


def _format_structured_sections(lines: list[str]) -> list[tuple[str, str]] | None:
    """
    处理形如：
    （1）概述 / （一）概述
    xxxx
    （2）核心意义
    yyyy
    的结构化段落（兜底路径）。
    """
    items: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        m = _CN_SECTION_ANY_RE.match(ln) or _CN_SECTION_RE.match(ln)
        if not m:
            i += 1
            continue
        title = m.group("title").strip()
        i += 1
        buf: list[str] = []
        while i < len(lines):
            nxt = lines[i]
            nxs = nxt.strip()
            if _CN_SECTION_ANY_RE.match(nxs) or _CN_SECTION_RE.match(nxs):
                break
            if nxs:
                buf.append(_bulletize_pasted_line(nxt))
            i += 1
        value = "\n".join(buf).strip()
        if title and value:
            items.append((title, value))
    return items or None


def _format_markdown(entry: Entry) -> str:
    block = _normalize_unicode_text(entry.raw_block).strip()
    lines = [ln.rstrip() for ln in block.splitlines()]

    if lines:
        first = lines[0].strip()
        if first.startswith("##"):
            lines = lines[1:]

    if lines and _MINOR_ENTITY_HEAD_RE.match(lines[0].strip()):
        lines = lines[1:]

    # 仅当首行编号标题与条目名相同时去掉（避免误删「1．概述」）
    if lines:
        first2 = lines[0].strip()
        mnum = _NUMBERED_ITEM_RE.match(first2)
        if mnum and mnum.group("title").strip() == entry.name.strip():
            lines = lines[1:]

    preamble, subsections = _split_preamble_and_subsections(lines)
    preamble = _trim_redundant_preamble(preamble, entry.name)

    if subsections:
        parts: list[str] = [f"## {entry.name}", ""]
        if preamble:
            parts.append(_refine_plain_lines_to_kv_bullets(preamble))
            parts.append("")
        for title, value in subsections:
            body = _refine_plain_lines_to_kv_bullets(value)
            body = _strip_leading_title_echo(body, title)
            if not body.strip():
                continue
            parts.append(f"### {title}")
            parts.append("")
            parts.append(body)
            parts.append("")
        return "\n".join(parts).rstrip() + "\n"

    if preamble:
        body = _refine_plain_lines_to_kv_bullets(preamble)
        body = _strip_leading_title_echo(body, entry.name)
        if not body.strip():
            return f"## {entry.name}\n\n"
        return f"## {entry.name}\n\n{body}\n"

    structured = _format_structured_sections(lines)
    kvs = structured if structured is not None else _parse_kv_lines(lines)
    rest_text_lines = [
        ln
        for ln in lines
        if ln.strip()
        and _line_section_header_title(ln) is None
        and ln.strip().lstrip("-*").strip()
        and ("：" not in ln and ":" not in ln)
    ]

    out: list[str] = [f"## {entry.name}"]
    if kvs:
        out.append("")
        for k, v in kvs:
            v2 = _refine_plain_lines_to_kv_bullets(v) if v else v
            v2 = _strip_leading_title_echo(v2 or "", k)
            if not (v2 or "").strip():
                continue
            if "\n" in v2 and v2.lstrip().startswith("- "):
                out.append(f"- **{k}**：")
                out.extend([f"  {ln}" for ln in v2.splitlines()])
            else:
                out.append(f"- **{k}**：{v2}")
    if rest_text_lines:
        out.append("")
        rest_blob = _strip_leading_title_echo("\n".join(rest_text_lines), entry.name)
        if rest_blob:
            for ln in rest_blob.split("\n"):
                if ln.strip():
                    out.append(_bulletize_pasted_line(ln))

    out.append("")
    return "\n".join(out).rstrip() + "\n"


def _resolve_output_dir(type_name: str) -> Path:
    rel = TYPE_DIR_MAP.get(_normalize_type_name(type_name), TYPE_DIR_MAP["未分类"])
    return PROJECT_ROOT / rel


def _remove_empty_nested_dirs_under_type_root(type_root: Path) -> int:
    """
    仅删除 type_root 之下的空子目录（由深到浅），不删除 type_root 本身。
    type_root 必须在白名单内，否则 noop。
    """
    try:
        root = type_root.resolve()
    except OSError:
        return 0
    if root not in _CANONICAL_TYPE_ROOTS:
        return 0
    if not root.is_dir():
        return 0
    removed = 0
    subdirs = [p for p in root.rglob("*") if p.is_dir()]
    subdirs.sort(key=lambda p: len(p.parts), reverse=True)
    for d in subdirs:
        try:
            if not any(d.iterdir()):
                d.rmdir()
                removed += 1
        except OSError:
            continue
    return removed


def _cleanup_empty_subdirs_for_entries(entries: list[Entry]) -> int:
    """对本次拆分涉及的类型目录分别清理空子文件夹，返回删除的目录数量。"""
    touched: set[Path] = {_resolve_output_dir(e.type_name) for e in entries}
    total = 0
    for tr in touched:
        total += _remove_empty_nested_dirs_under_type_root(tr)
    return total


def _write_entry(entry: Entry) -> Path:
    out_dir = _resolve_output_dir(entry.type_name)
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

    outline = _split_outline_entities(text)
    if outline:
        expanded_hinted: list[tuple[str, str | None]] = []
        for oblock, hint in outline:
            for sub in _split_numbered_items(oblock):
                expanded_hinted.append((sub, hint))
        entries = [_parse_entry(b, type_hint=h) for b, h in expanded_hinted]
    else:
        blocks = _split_blocks(text)
        if not blocks:
            return "setting-splitter 未发现可处理的段落块（请确保段落之间用空行分隔）。"

        expanded: list[str] = []
        for b in blocks:
            expanded.extend(_split_numbered_items(b))

        entries = [_parse_entry(b) for b in expanded]
    written: list[Path] = []
    for e in entries:
        written.append(_write_entry(e))

    removed_dirs = _cleanup_empty_subdirs_for_entries(entries)

    lines = [f"已执行技能 setting-splitter，共拆分并写入 {len(written)} 个文件："]
    for p in written:
        try:
            rel = p.relative_to(PROJECT_ROOT)
            lines.append(f"- {rel.as_posix()}")
        except Exception:
            lines.append(f"- {str(p)}")
    if removed_dirs:
        lines.append(f"（已在本次写入涉及的类型目录下移除 {removed_dirs} 个空子文件夹）")
    return "\n".join(lines)


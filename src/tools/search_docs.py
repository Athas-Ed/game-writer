import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple


"""
SearchDocs：用于“字段/段落级修改”的专用检索工具。

它会在 `data/**/*.md` 内把文档按标题/段落切片，然后对切片做轻量关键词相似度检索，
返回 top-k 证据片段（含文件路径与片段内容），供 LLM 再决定下一步调用 ReadFile 读取整文件。

可升级为向量+RAG，支持处理上万的md文件。
"""


PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_ROOT = PROJECT_ROOT / "data"

_SUPPORTED_EXTS = {".md"}
_MAX_SNIPPET_CHARS = 900
_SLICE_OVERLAP_CHARS = 120


@dataclass(frozen=True)
class _Chunk:
    rel_path: str
    heading: str
    text: str
    norm_text: str
    tokens: Tuple[str, ...]


_CHUNKS_CACHE: Optional[List[_Chunk]] = None
_DATA_MTIME: Optional[float] = None

# 额外：文件名/路径 token -> 文件集合，用于快速缩小候选
_FILE_TOKEN_INDEX: Optional[Dict[str, Set[str]]] = None


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
    # 去掉大量分隔符，方便做短文本相似度
    s = re.sub(r"[\s\-_·。。，、；;:：!?！？()\[\]{}\"'“”]+", "", s)
    return s


def _tokenize(s: str) -> List[str]:
    """
    用一个比较宽松的规则分词：
    - 连续中文/数字/字母/下划线作为一个 token
    - 以此保证“年龄”“18”“温特菲尔德”等能参与匹配
    """
    s = s or ""
    return re.findall(r"[\u4e00-\u9fffA-Za-z0-9_]+", s)


def _chunk_markdown(text: str, *, min_chars: int = 120) -> List[Tuple[str, str]]:
    """
    按标题切片；没有标题时按段落切片。
    返回：[(heading, chunk_text), ...]
    """
    # 标题切片（兼容 "#", "##", ...）
    heading_pat = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
    matches = list(heading_pat.finditer(text or ""))

    chunks: List[Tuple[str, str]] = []
    if matches:
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            heading_text = m.group(2).strip()
            chunk_text = text[start:end].strip()
            if len(chunk_text) >= min_chars:
                chunks.append((heading_text, chunk_text))
        return chunks

    # 无标题：按空行分段
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    buf: List[str] = []
    cur_len = 0
    for p in paras:
        if cur_len + len(p) > 1200 and buf:
            combined = "\n\n".join(buf).strip()
            if len(combined) >= min_chars:
                chunks.append(("段落块", combined))
            buf = [p]
            cur_len = len(p)
        else:
            buf.append(p)
            cur_len += len(p)
    if buf:
        combined = "\n\n".join(buf).strip()
        if len(combined) >= min_chars:
            chunks.append(("段落块", combined))
    return chunks


def _build_index() -> Tuple[List[_Chunk], Dict[str, Set[str]]]:
    chunks: List[_Chunk] = []
    file_token_index: Dict[str, Set[str]] = {}

    if not DATA_ROOT.exists() or not DATA_ROOT.is_dir():
        return chunks, file_token_index

    for path in DATA_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _SUPPORTED_EXTS:
            continue
        rel_path = path.relative_to(PROJECT_ROOT).as_posix()
        text = _safe_read_text(path)
        if not text.strip():
            continue

        # 文件路径 token 建索引：用于缩小候选
        for tok in set(_tokenize(rel_path)):
            file_token_index.setdefault(tok, set()).add(rel_path)

        for heading, chunk_text in _chunk_markdown(text):
            norm = _normalize(chunk_text)
            toks = tuple(_tokenize(chunk_text))
            if not toks:
                continue
            chunks.append(
                _Chunk(
                    rel_path=rel_path,
                    heading=heading,
                    text=chunk_text,
                    norm_text=norm,
                    tokens=toks,
                )
            )
    return chunks, file_token_index


def _get_index() -> Tuple[List[_Chunk], Dict[str, Set[str]]]:
    global _CHUNKS_CACHE, _DATA_MTIME, _FILE_TOKEN_INDEX
    try:
        current_mtime = DATA_ROOT.stat().st_mtime
    except Exception:
        current_mtime = None

    # 如果 data/ 没变，直接复用缓存
    if _CHUNKS_CACHE is not None and _DATA_MTIME == current_mtime:
        return _CHUNKS_CACHE, _FILE_TOKEN_INDEX or {}

    _DATA_MTIME = current_mtime

    chunks, file_token_index = _build_index()
    _CHUNKS_CACHE = chunks
    _FILE_TOKEN_INDEX = file_token_index
    return chunks, file_token_index


def _score_chunk(query_tokens: Sequence[str], query_norm: str, chunk: _Chunk) -> float:
    if not query_tokens:
        return 0.0
    chunk_tokens = set(chunk.tokens)
    q_set = set(query_tokens)
    overlap = q_set.intersection(chunk_tokens)
    token_ratio = len(overlap) / max(1, len(q_set))

    # 如果 query_norm 作为子串出现在 chunk_norm，说明命中更强
    sub_bonus = 0.0
    if query_norm and query_norm in chunk.norm_text:
        sub_bonus = 0.35

    # 短字符串相似度（用 normalize 后的文本）
    # 这里不做 difflib 全量比对（太慢），只用一个轻量比例：
    # 共同 token 数越多，分数越高；并略微结合 norm_text 前 200 字符。
    head_len = min(200, len(chunk.norm_text))
    head_norm = chunk.norm_text[:head_len]
    head_ratio = 0.0
    if query_norm and head_norm:
        # 只要 query_norm 过短也会被 boost，避免误伤太多
        if len(query_norm) >= 4:
            common_chars = set(query_norm).intersection(head_norm)
            head_ratio = len(common_chars) / max(1, len(set(query_norm)))

    return 0.65 * token_ratio + sub_bonus + 0.15 * head_ratio


def _extract_snippet(chunk_text: str, query_tokens: Sequence[str]) -> str:
    if not chunk_text:
        return ""
    if not query_tokens:
        # 兜底：截取开头
        return chunk_text[:_MAX_SNIPPET_CHARS]

    # 优先使用较长 token 定位
    candidates = sorted(query_tokens, key=lambda x: len(x), reverse=True)
    pos = -1
    for tok in candidates:
        if not tok:
            continue
        idx = chunk_text.find(tok)
        if idx >= 0:
            pos = idx
            break
        # 对数字/英文也尝试大小写无关
        idx2 = chunk_text.lower().find(tok.lower())
        if idx2 >= 0:
            pos = idx2
            break

    if pos < 0:
        # 找不到就截断中间段
        start = max(0, (len(chunk_text) - _MAX_SNIPPET_CHARS) // 2)
        end = start + _MAX_SNIPPET_CHARS
        return chunk_text[start:end]

    start = max(0, pos - _SLICE_OVERLAP_CHARS)
    end = min(len(chunk_text), pos + _MAX_SNIPPET_CHARS - _SLICE_OVERLAP_CHARS)
    snippet = chunk_text[start:end].strip()
    return snippet


def search_docs(query: str, top_k: int = 8) -> str:
    """
    输入：
    - query: 用户想修改/定位的关键词（例如“艾莉丝 年龄 18岁”或“艾莉丝 年龄”）
    输出：
    - top-k 证据片段（含文件路径 + 片段内容），供 Agent 再决定 ReadFile + WriteFile
    """
    q = (query or "").strip()
    if not q:
        return "SearchDocs：query 为空。"

    chunks, file_token_index = _get_index()

    query_tokens = [t for t in _tokenize(q) if t.strip()]
    query_norm = _normalize(q)

    # 先用路径 token 缩小候选（加速）
    candidate_files: Optional[Set[str]] = None
    for tok in set(query_tokens):
        if tok in file_token_index:
            s = file_token_index[tok]
            candidate_files = s if candidate_files is None else (candidate_files | s)

    if candidate_files is not None and candidate_files:
        candidates = [c for c in chunks if c.rel_path in candidate_files]
    else:
        candidates = chunks

    scored: List[Tuple[float, _Chunk]] = []
    for ch in candidates:
        score = _score_chunk(query_tokens, query_norm, ch)
        if score <= 0:
            continue
        scored.append((score, ch))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[: max(1, int(top_k))]

    if not top:
        return "SearchDocs：未找到匹配证据。你可以换一个更具体的关键词（字段名/角色名/数字）。"

    out_lines: List[str] = []
    out_lines.append(f"SearchDocs结果（top-{len(top)}）：")
    for i, (score, ch) in enumerate(top, start=1):
        snippet = _extract_snippet(ch.text, query_tokens)
        out_lines.append(f"{i}) 分数={score:.3f}")
        out_lines.append(f"   文件={ch.rel_path}")
        out_lines.append(f"   标题={ch.heading}")
        out_lines.append("   片段如下：")
        out_lines.append(snippet)
        out_lines.append("")  # blank line

    out_lines.append("建议下一步：请用 ReadFile 读取对应文件（文件路径），然后在文件内修改目标字段/段落。")
    return "\n".join(out_lines).strip()


import re
from typing import List, Optional, Sequence, Set, Tuple

from src.tools.data_chunks import ChunkRecord, get_data_chunks_index

"""
SearchDocs：用于“字段/段落级修改”的专用检索工具。

在 `data/**/*.md` 分块索引上做轻量关键词相似度检索，
返回 top-k 证据片段（含文件路径与片段内容），供 LLM 再决定下一步调用 ReadFile 读取整文件。

分块与元数据由 `data_chunks` 统一维护，可在此基础上升级为向量+RAG。
"""

_MAX_SNIPPET_CHARS = 900
_SLICE_OVERLAP_CHARS = 120


def _score_chunk(query_tokens: Sequence[str], query_norm: str, chunk: ChunkRecord) -> float:
    if not query_tokens:
        return 0.0
    chunk_tokens = set(chunk.tokens)
    q_set = set(query_tokens)
    overlap = q_set.intersection(chunk_tokens)
    token_ratio = len(overlap) / max(1, len(q_set))

    sub_bonus = 0.0
    if query_norm and query_norm in chunk.norm_text:
        sub_bonus = 0.35

    head_len = min(200, len(chunk.norm_text))
    head_norm = chunk.norm_text[:head_len]
    head_ratio = 0.0
    if query_norm and head_norm:
        if len(query_norm) >= 4:
            common_chars = set(query_norm).intersection(head_norm)
            head_ratio = len(common_chars) / max(1, len(set(query_norm)))

    return 0.65 * token_ratio + sub_bonus + 0.15 * head_ratio


def _extract_snippet(chunk_text: str, query_tokens: Sequence[str]) -> str:
    if not chunk_text:
        return ""
    if not query_tokens:
        return chunk_text[:_MAX_SNIPPET_CHARS]

    candidates = sorted(query_tokens, key=lambda x: len(x), reverse=True)
    pos = -1
    for tok in candidates:
        if not tok:
            continue
        idx = chunk_text.find(tok)
        if idx >= 0:
            pos = idx
            break
        idx2 = chunk_text.lower().find(tok.lower())
        if idx2 >= 0:
            pos = idx2
            break

    if pos < 0:
        start = max(0, (len(chunk_text) - _MAX_SNIPPET_CHARS) // 2)
        end = start + _MAX_SNIPPET_CHARS
        return chunk_text[start:end]

    start = max(0, pos - _SLICE_OVERLAP_CHARS)
    end = min(len(chunk_text), pos + _MAX_SNIPPET_CHARS - _SLICE_OVERLAP_CHARS)
    return chunk_text[start:end].strip()


def _tokenize_query(q: str) -> List[str]:
    s = q or ""
    return re.findall(r"[\u4e00-\u9fffA-Za-z0-9_]+", s)


def _normalize_query(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[\s\-_·。。，、；;:：!?！？()\[\]{}\"'“”]+", "", s)
    return s


def _scored_chunks_for_query(query: str) -> Tuple[List[str], List[Tuple[float, ChunkRecord]]]:
    """对剧情句/关键词打分排序，供 SearchDocs 与 gather_evidence_context 共用。"""
    q = (query or "").strip()
    if not q:
        return [], []

    chunks, file_token_index = get_data_chunks_index()
    query_tokens = [t for t in _tokenize_query(q) if t.strip()]
    query_norm = _normalize_query(q)
    if not query_tokens:
        return [], []

    candidate_files: Optional[Set[str]] = None
    for tok in set(query_tokens):
        if tok in file_token_index:
            s = file_token_index[tok]
            candidate_files = s if candidate_files is None else (candidate_files | s)

    if candidate_files is not None and candidate_files:
        candidates = [c for c in chunks if c.rel_path in candidate_files]
    else:
        candidates = chunks

    scored: List[Tuple[float, ChunkRecord]] = []
    for ch in candidates:
        score = _score_chunk(query_tokens, query_norm, ch)
        if score <= 0:
            continue
        scored.append((score, ch))

    scored.sort(key=lambda x: x[0], reverse=True)
    return query_tokens, scored


def gather_evidence_context(
    query: str,
    *,
    top_k: int = 16,
    max_total_chars: int = 26_000,
) -> str:
    """
    供 outline-writer 等内部调用：检索 data 下分块并拼接**完整块正文**，用于 LLM 上下文。
    无命中时返回空字符串。
    """
    _, scored = _scored_chunks_for_query(query)
    if not scored:
        return ""

    top = scored[: max(1, int(top_k))]
    parts: List[str] = []
    total = 0
    seen_ref: Set[str] = set()
    for score, ch in top:
        ref = ch.chunk_ref
        if ref in seen_ref:
            continue
        seen_ref.add(ref)
        block = (
            f"### {ch.rel_path}（chunk_ref={ch.chunk_ref} | data_category={ch.data_category} | "
            f"标题: {ch.heading} | score={score:.3f}）\n\n{ch.text}\n\n"
        )
        if total + len(block) > max_total_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n".join(parts).strip()


def search_docs(query: str, top_k: int = 8) -> str:
    """
    输入：
    - query: 用户想修改/定位的关键词（例如“艾莉丝 年龄 18岁”或“艾莉丝 年龄”）
    输出：
    - top-k 证据片段（含文件路径 + chunk_ref + 片段内容），供 Agent 再决定 ReadFile + WriteFile
    """
    q = (query or "").strip()
    if not q:
        return "SearchDocs：query 为空。"

    query_tokens, scored = _scored_chunks_for_query(q)
    if not query_tokens:
        return "SearchDocs：请使用中文、英文或数字关键词（当前 query 无法分词）。"

    top = scored[: max(1, int(top_k))]

    if not top:
        return "SearchDocs：未找到匹配证据。你可以换一个更具体的关键词（字段名/角色名/数字），或先用 SettingsRoute list 浏览索引。"

    out_lines: List[str] = []
    out_lines.append(f"SearchDocs结果（top-{len(top)}）：")
    for i, (score, ch) in enumerate(top, start=1):
        snippet = _extract_snippet(ch.text, query_tokens)
        out_lines.append(f"{i}) 分数={score:.3f}")
        out_lines.append(f"   文件={ch.rel_path}")
        out_lines.append(f"   chunk_ref={ch.chunk_ref}")
        out_lines.append(f"   data_category={ch.data_category}")
        out_lines.append(f"   标题={ch.heading}")
        out_lines.append("   片段如下：")
        out_lines.append(snippet)
        out_lines.append("")

    out_lines.append("建议下一步：用 ReadFile 读取对应文件，或使用 SettingsRoute chunks path=… 查看完整分块。")
    return "\n".join(out_lines).strip()

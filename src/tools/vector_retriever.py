from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.tools.data_chunks import get_data_chunks_index
from src.tools.search_docs import gather_evidence_context

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_ROOT = PROJECT_ROOT / "data"
INDEX_DIR = PROJECT_ROOT / ".vector_index"  # chromadb 持久化目录
_DEFAULT_LOCAL_MODEL_DIR = PROJECT_ROOT / "models" / "bge-small-zh-v1.5"

_model = None
_client = None


def get_embedding_model():
    """
    获取 SentenceTransformer embedding 模型（懒加载 + 单例）。

    可通过环境变量调整模型：
    - `VECTOR_EMBED_MODEL`（默认：`BAAI/bge-small-zh-v1.5`）
    """

    global _model
    if _model is not None:
        return _model

    # Windows 上有些环境会残留 SSL_CERT_FILE，但路径已失效，导致 httpx/transformers 直接崩溃。
    # 这里做“最小自愈”：若 SSL_CERT_FILE 指向不存在的文件，则尝试改用 certifi；否则直接移除该变量。
    ssl_cert_file = os.getenv("SSL_CERT_FILE")
    if ssl_cert_file and not Path(ssl_cert_file).exists():
        try:
            import certifi  # type: ignore

            os.environ["SSL_CERT_FILE"] = certifi.where()
        except Exception:
            os.environ.pop("SSL_CERT_FILE", None)

    try:
        from sentence_transformers import SentenceTransformer
    except Exception as e:
        raise RuntimeError(
            "缺少依赖 `sentence-transformers`。请先在当前虚拟环境安装：pip install sentence-transformers"
        ) from e

    model_name = os.getenv("VECTOR_EMBED_MODEL", "").strip()
    if not model_name:
        # 优先使用项目内本地模型，避免在受限网络环境下默认联网拉取。
        if _DEFAULT_LOCAL_MODEL_DIR.exists() and _DEFAULT_LOCAL_MODEL_DIR.is_dir():
            model_name = str(_DEFAULT_LOCAL_MODEL_DIR)
        else:
            model_name = "BAAI/bge-small-zh-v1.5"

    # 可选：在证书链无法校验的网络环境（公司代理/抓包证书）下，允许显式关闭 HF 下载的 SSL 校验。
    # 默认关闭；仅当用户明确设置 VECTOR_INSECURE_SSL=1 才启用。
    if os.getenv("VECTOR_INSECURE_SSL", "0").strip() in {"1", "true", "yes"}:
        os.environ.setdefault("HF_HUB_DISABLE_SSL_VERIFICATION", "1")

    try:
        _model = SentenceTransformer(model_name)
    except Exception as e:
        # 给出可操作的提示：要么修复证书链，要么改用本地模型路径，要么（不推荐）临时关闭校验。
        hint = (
            f"加载向量模型失败：{model_name}\n"
            "常见原因：无法验证 https://huggingface.co 的证书链（CERTIFICATE_VERIFY_FAILED）。\n\n"
            "你可以选一种方式解决：\n"
            "1) 推荐：修复网络/证书\n"
            "   - 确保公司代理已安装根证书到系统；或关闭 HTTPS 抓包。\n"
            "   - 确保环境里未错误设置 HTTP(S)_PROXY；必要时清空后再试。\n"
            "2) 使用本地模型：把模型下载到本地目录后，设置环境变量 VECTOR_EMBED_MODEL=本地路径。\n"
            "3) 临时（不推荐）：跳过 SSL 校验：设置 VECTOR_INSECURE_SSL=1 后重试。\n"
        )
        raise RuntimeError(hint) from e
    return _model


def get_chroma_client():
    """获取 chromadb PersistentClient（懒加载 + 单例）。"""

    global _client
    if _client is not None:
        return _client

    try:
        import chromadb
    except Exception as e:
        raise RuntimeError("缺少依赖 `chromadb`。请先在当前虚拟环境安装：pip install chromadb") from e

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=str(INDEX_DIR))
    return _client


def _collection_name() -> str:
    # 使用 v1 后缀，避免和旧格式（旧 chunk_id 规则）混用
    return os.getenv("VECTOR_COLLECTION", "game_settings_chunks_v1")


def _manifest_path() -> Path:
    return INDEX_DIR / "manifest.json"


def _current_data_signature() -> Dict[str, Any]:
    """基于 data/ 目录的 mtime + chunk 数做轻量签名，用于决定是否重建索引。"""

    try:
        mtime = DATA_ROOT.stat().st_mtime
    except Exception:
        mtime = None

    # get_data_chunks_index 内部带缓存，这里不会太慢
    records, _ = get_data_chunks_index()
    return {
        "data_mtime": mtime,
        "chunk_count": len(records),
        "embed_model": os.getenv("VECTOR_EMBED_MODEL", "BAAI/bge-small-zh-v1.5"),
    }


def _load_manifest() -> Dict[str, Any]:
    p = _manifest_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_manifest(sig: Dict[str, Any]) -> None:
    p = _manifest_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(sig, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def build_index(*, force_rebuild: bool = False):
    """
    从 `src/tools/data_chunks.py` 的分块数据生成向量索引，并持久化到 chromadb。

    输出：chromadb collection。
    """

    client = get_chroma_client()
    name = _collection_name()

    if force_rebuild:
        try:
            client.delete_collection(name)
        except Exception:
            pass

    try:
        # 已存在时直接复用（除非外部要求强制重建）
        collection = client.get_collection(name)
        if not force_rebuild:
            return collection
    except Exception:
        pass

    # Rebuild: 重新创建并写入向量
    collection = client.create_collection(name=name)

    records, _ = get_data_chunks_index()
    if not records:
        # data/ 下无可分块内容
        _save_manifest(_current_data_signature())
        return collection

    model = get_embedding_model()

    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    for r in records:
        ids.append(r.chunk_ref)
        documents.append(r.text)
        metadatas.append(
            {
                "source": r.rel_path,
                "chunk_ref": r.chunk_ref,
                "data_category": r.data_category,
                "heading": r.heading,
                "heading_level": r.heading_level,
            }
        )

    batch_size = int(os.getenv("VECTOR_BATCH_SIZE", "64"))
    embeddings = model.encode(
        documents,
        batch_size=batch_size,
        show_progress_bar=True,
    )

    # chromadb 通常接受 list[list[float]]
    try:
        emb_list = embeddings.tolist()
    except Exception:
        emb_list = embeddings  # type: ignore[assignment]

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=emb_list,
    )

    _save_manifest(_current_data_signature())
    return collection


def ensure_index(*, force_rebuild: bool = False):
    """确保向量索引存在且与当前 data/ 状态匹配。"""

    client = get_chroma_client()
    name = _collection_name()

    if force_rebuild:
        return build_index(force_rebuild=True)

    manifest = _load_manifest()
    desired_sig = _current_data_signature()

    auto_rebuild = os.getenv("VECTOR_AUTO_REBUILD", "1").strip() != "0"
    try:
        collection = client.get_collection(name)
        if not auto_rebuild:
            return collection

        # manifest 不一致 => 重建
        if manifest and manifest != desired_sig:
            return build_index(force_rebuild=True)

        return collection
    except Exception:
        return build_index(force_rebuild=True)


def retrieve(query: str, top_k: int = 5) -> List[Tuple[str, str, str, float]]:
    """
    语义检索。

    返回：[(chunk_text, source_rel_path, chunk_ref, similarity), ...]
    """

    q = (query or "").strip()
    if not q:
        return []

    collection = ensure_index()
    model = get_embedding_model()
    query_embedding = model.encode([q]).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=int(top_k),
        include=["documents", "metadatas", "distances"],
    )

    retrieved: List[Tuple[str, str, str, float]] = []
    docs = (results.get("documents") or [[]])[0] or []
    metas = (results.get("metadatas") or [[]])[0] or []
    dists = (results.get("distances") or [[]])[0] or []

    for i in range(len(docs)):
        doc = docs[i]
        meta = metas[i] if i < len(metas) else {}
        dist = dists[i] if i < len(dists) else None

        # chromadb 的距离越小越相似；这里做简单映射到 [0,1) 以便展示
        similarity = 1 / (1 + dist) if dist is not None else 0.0

        retrieved.append(
            (
                str(doc),
                str(meta.get("source", "未知")),
                str(meta.get("chunk_ref", "")),
                float(similarity),
            )
        )

    return retrieved


def retrieve_context(query: str, top_k: int = 5, *, max_total_chars: int = 26_000) -> str:
    """供 Agent 调用的便捷函数：返回格式化的检索结果（用于上下文拼接/后续 ReadFile 精读）。"""

    rag_enabled = os.getenv("RAG_ENABLED", "0").strip() in {"1", "true", "yes"}
    if not rag_enabled:
        fallback = gather_evidence_context(
            query,
            top_k=max(8, int(top_k) * 2),
            max_total_chars=max_total_chars,
        )
        if not fallback:
            return "未找到相关设定。"
        return "【RAG 增强模式未开启：使用关键词证据检索】\n\n" + fallback.strip()

    try:
        results = retrieve(query, top_k=top_k)
    except Exception as e:
        # 典型场景：公司代理/证书链问题导致 HuggingFace 模型无法下载。
        # 为保证工具可用，这里自动降级为现有关键词证据检索（同样带 chunk_ref）。
        fallback = gather_evidence_context(
            query,
            top_k=max(8, int(top_k) * 2),
            max_total_chars=max_total_chars,
        )
        if not fallback:
            return f"向量检索不可用（{e}），且未找到相关设定。"
        return "【向量检索暂不可用，已降级为关键词证据检索】\n\n" + fallback.strip()
    if not results:
        return "未找到相关设定。"

    context = "【向量检索结果】\n\n"
    total = 0
    for i, (doc, source, chunk_ref, sim) in enumerate(results, 1):
        block = f"### {i}) 来源：{source}（chunk_ref={chunk_ref} | 相似度 {sim:.2f}）\n{doc}\n\n"
        if total + len(block) > max_total_chars:
            break
        context += block
        total += len(block)

    return context.strip()


if __name__ == "__main__":
    # 手动测试：强制重建索引并输出检索结果
    build_index(force_rebuild=True)
    print(retrieve_context("林夕", top_k=5))
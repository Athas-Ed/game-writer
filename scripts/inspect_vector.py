import os


def main() -> None:
    from src.tools.data_chunks import get_data_chunks_index
    from src.tools.vector_retriever import ensure_index, retrieve

    chunks, _ = get_data_chunks_index()
    print("chunk_count", len(chunks))
    if chunks:
        print("first_chunk_ref", chunks[0].chunk_ref)
        print("first_rel_path", chunks[0].rel_path)
        print("first_heading", chunks[0].heading)
        print("first_char_count", len(chunks[0].text))

    col = ensure_index()
    try:
        print("collection_name", col.name)
    except Exception:
        pass
    try:
        print("collection_count", col.count())
    except Exception as e:
        print("collection_count_error", repr(e))

    q = os.getenv("INSPECT_QUERY", "卡姆罗")
    print("query", q)
    res = retrieve(q, top_k=3)
    print("hits", len(res))
    for i, (doc, source, chunk_ref, sim) in enumerate(res, start=1):
        print(f"{i}) sim={sim:.3f} source={source} chunk_ref={chunk_ref} doc_head={doc[:60]!r}")


if __name__ == "__main__":
    main()


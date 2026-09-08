from server.retrieval.reranker import rerank


def test_rerank_orders_chunks_by_relevance_to_query():
    query = "What was Nvidia's data center revenue?"
    chunks = [
        {"chunk_id": "c1", "text": "The weather in California was sunny this quarter."},
        {"chunk_id": "c2", "text": "Nvidia data center revenue reached $9 billion in Q1 2026."},
    ]

    results = rerank(query, chunks, top_k=2)

    assert results[0]["chunk_id"] == "c2"  # more relevant chunk ranked first
    assert len(results) == 2


def test_rerank_respects_top_k():
    query = "Nvidia revenue"
    chunks = [
        {"chunk_id": f"c{i}", "text": f"Nvidia revenue figure number {i}"} for i in range(5)
    ]

    results = rerank(query, chunks, top_k=2)

    assert len(results) == 2

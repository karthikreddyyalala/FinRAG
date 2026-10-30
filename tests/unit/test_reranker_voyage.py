"""TDD: the production reranker is Voyage's hosted cross-encoder.

Before this, the Lambda never installed sentence-transformers, so every live
search was ranked by the lexical fallback. Voyage takes over when its key is
set; any failure (outage, rate limit, bad key) falls back to the lexical
scorer so a search still returns passages.
"""
import json

import pytest
import responses

from server.retrieval import reranker
from server.retrieval.reranker import VOYAGE_URL, rerank

CHUNKS = [
    {"chunk_id": "weather", "text": "The weather in California was sunny."},
    {"chunk_id": "revenue", "text": "Nvidia data center revenue reached $9 billion."},
    {"chunk_id": "table", "text": "x" * 20_000},
]


@pytest.fixture
def voyage_key(monkeypatch):
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")


@responses.activate
def test_voyage_order_is_used(voyage_key):
    responses.post(VOYAGE_URL, json={"data": [
        {"index": 2, "relevance_score": 0.9},
        {"index": 0, "relevance_score": 0.5},
    ]})

    results = rerank("Nvidia data center revenue?", CHUNKS, top_k=2)

    assert [c["chunk_id"] for c in results] == ["table", "weather"]
    body = json.loads(responses.calls[0].request.body)
    assert body["model"] == reranker.VOYAGE_MODEL
    assert body["query"] == "Nvidia data center revenue?"
    assert body["top_k"] == 2
    # Long tables are cut to what the client would see anyway.
    assert len(body["documents"][2]) == reranker.MAX_DOC_CHARS
    assert responses.calls[0].request.headers["Authorization"] == "Bearer test-key"


@responses.activate
def test_voyage_failure_falls_back_to_lexical(voyage_key, capsys):
    responses.post(VOYAGE_URL, status=429, json={"detail": "rate limited"})

    results = rerank("Nvidia data center revenue?", CHUNKS[:2], top_k=1)

    assert [c["chunk_id"] for c in results] == ["revenue"]
    assert "lexical" in capsys.readouterr().out


@responses.activate
def test_no_key_means_no_network_call():
    results = rerank("Nvidia data center revenue?", CHUNKS[:2], top_k=1)

    assert [c["chunk_id"] for c in results] == ["revenue"]
    assert len(responses.calls) == 0

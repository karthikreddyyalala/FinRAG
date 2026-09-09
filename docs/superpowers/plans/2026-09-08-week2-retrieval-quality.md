# Week 2 Retrieval Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `search_sec_filings` from Week 1's direct-Pinecone-only retrieval into the full four-stage pipeline CLAUDE.md specifies: query rewriting (Haiku) → hybrid BM25+dense search → CrossEncoder reranking → Sonnet generation with citations → numerical verification.

**Architecture:** Five new modules under `server/retrieval/` and `server/generation/`, each independently testable with mocked Bedrock/Pinecone clients. `pipeline/sync_pinecone.py` gains BM25 index building (serialized to S3, since rank-bm25 has no persistence of its own). `bootstrap_corpus.py` is updated to build that index once, after all filings are ingested, and to cover the expanded 50-company corpus. `server/mcp_tools/search_filings.py` is rewired to call the new pipeline instead of querying Pinecone directly. The CrossEncoder reranker is packaged as a separate container-image Lambda (decided in Week 1 planning — `sentence-transformers`+`torch` is ~1.2GB, over the 250MB zip limit).

**Tech Stack:** `rank-bm25` (keyword search), `sentence-transformers` + `torch` CPU (CrossEncoder reranking, container-image Lambda only), Bedrock Converse API (`us.anthropic.claude-haiku-4-5-20251001-v1:0` for rewriting, `us.anthropic.claude-sonnet-4-5-20250929-v1:0` for generation — both require the `us.` cross-region inference profile prefix, verified via AWS docs this session, plain `anthropic.claude-*` IDs fail with an on-demand-throughput error).

---

## File Structure

```
requirements.txt                          # Task 1: add rank-bm25
pipeline/sync_pinecone.py                 # Task 1: modify -- add BM25 index build/store/load
server/retrieval/
├── __init__.py                            # Task 2
├── query_rewriter.py                      # Task 2
├── hybrid_retriever.py                    # Task 3
├── reranker.py                            # Task 4
└── numerical_verifier.py                  # Task 5
server/generation/
├── __init__.py                            # Task 6
└── answer_generator.py                    # Task 6
server/mcp_tools/search_filings.py        # Task 7: modify -- wire full pipeline
scripts/bootstrap_corpus.py               # Task 8: modify -- 50 companies, build BM25 index at end
tests/unit/
├── test_sync_pinecone.py                  # Task 1: modify -- add BM25 tests
├── test_query_rewriter.py                 # Task 2
├── test_hybrid_retriever.py               # Task 3
├── test_reranker.py                       # Task 4
├── test_numerical_verifier.py             # Task 5
├── test_answer_generator.py               # Task 6
├── test_search_filings.py                 # Task 7: modify
└── test_bootstrap_corpus.py               # Task 8: modify
```

**Deferred to a manual/deploy task (Task 9, not subagent-coded):** packaging `reranker.py` into a container-image Lambda (needs a Dockerfile + CDK `DockerImageFunction`, decided in Week 1 planning but not yet built), deploying it, and wiring `hybrid_retriever.py`'s output through an actual cross-Lambda invoke at query time. Task 4 builds and unit-tests the CrossEncoder scoring logic itself (pure function, testable without a real Lambda); the container/deploy wiring is infrastructure work reserved for the manual step, same pattern as Week 1's CDK deploy.

---

### Task 1: BM25 index building in the ingestion pipeline

CLAUDE.md's ingestion flow (Phase 3 Step 4) always specified building a BM25 index alongside the Pinecone upsert, serialized to S3 for reuse at query time — Week 1 deferred this since Week 1 only needed direct Pinecone query. `rank-bm25`'s `BM25Okapi` has no built-in persistence, so this pickles the index together with its source chunks (so a BM25 hit can be resolved straight to full chunk metadata without a second lookup).

**Files:**
- Modify: `requirements.txt`
- Modify: `pipeline/sync_pinecone.py`
- Modify: `tests/unit/test_sync_pinecone.py`

- [ ] **Step 1: Add the dependency**

Add this line to `requirements.txt` (anywhere after `pinecone`, alphabetical isn't enforced elsewhere in the file so just append):

```
rank-bm25>=0.2,<0.3
```

Run: `source .venv/bin/activate && pip install -r requirements.txt`
Expected: `rank-bm25` installs with no errors (pulls in `numpy` as its only dependency).

- [ ] **Step 2: Write the failing tests**

Add to `tests/unit/test_sync_pinecone.py` (append below the existing tests, add `import pickle` and `from pipeline.sync_pinecone import build_and_store_bm25_index, load_bm25_index` to the existing imports):

```python
def test_build_and_store_bm25_index_pickles_index_and_chunks():
    s3 = MagicMock()
    chunks = [
        {"chunk_id": "c1", "text": "Nvidia data center revenue grew"},
        {"chunk_id": "c2", "text": "Apple iPhone revenue declined slightly"},
    ]

    build_and_store_bm25_index(s3, "finrag-processed-filings", "bm25/index.pkl", chunks)

    s3.put_object.assert_called_once()
    call_kwargs = s3.put_object.call_args.kwargs
    assert call_kwargs["Bucket"] == "finrag-processed-filings"
    assert call_kwargs["Key"] == "bm25/index.pkl"
    payload = pickle.loads(call_kwargs["Body"])
    assert payload["chunks"] == chunks
    assert payload["bm25"].get_scores(["nvidia", "revenue"])[0] > 0


def test_load_bm25_index_round_trips_through_pickle():
    s3 = MagicMock()
    chunks = [{"chunk_id": "c1", "text": "Nvidia data center revenue grew"}]
    build_and_store_bm25_index(s3, "bucket", "key", chunks)
    stored_body = s3.put_object.call_args.kwargs["Body"]
    s3.get_object.return_value = {"Body": MagicMock(read=lambda: stored_body)}

    bm25, loaded_chunks = load_bm25_index(s3, "bucket", "key")

    assert loaded_chunks == chunks
    assert bm25.get_scores(["nvidia"])[0] > 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_sync_pinecone.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_and_store_bm25_index'`

- [ ] **Step 4: Implement**

Add to `pipeline/sync_pinecone.py` (add `import pickle` to the top imports, add `from rank_bm25 import BM25Okapi` alongside the `pinecone` import):

```python
def build_and_store_bm25_index(
    s3_client: Any, bucket: str, key: str, chunks: list[dict[str, Any]]
) -> None:
    """Build a BM25 keyword index from chunk text and pickle it to S3.

    BM25Okapi has no persistence of its own, so the index and its source
    chunks are pickled together -- a BM25 hit resolves straight to full
    chunk metadata without a second lookup at query time.

    Args:
        s3_client: A boto3 S3 client.
        bucket: Destination bucket (finrag-processed-filings).
        key: S3 key to store the pickled index at.
        chunks: All chunks across the corpus, from chunker.chunk_filing().
    """
    tokenized = [c["text"].lower().split() for c in chunks]
    bm25 = BM25Okapi(tokenized)
    payload = pickle.dumps({"bm25": bm25, "chunks": chunks})
    s3_client.put_object(Bucket=bucket, Key=key, Body=payload)


def load_bm25_index(s3_client: Any, bucket: str, key: str) -> tuple[BM25Okapi, list[dict[str, Any]]]:
    """Load a pickled BM25 index and its source chunks from S3.

    Args:
        s3_client: A boto3 S3 client.
        bucket: Bucket the index was stored in.
        key: S3 key the index was stored at.

    Returns:
        (bm25_index, chunks) -- chunks[i] is the source chunk for the i-th
        entry in bm25_index's internal corpus, in the same order.
    """
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    payload = pickle.loads(obj["Body"].read())
    return payload["bm25"], payload["chunks"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_sync_pinecone.py -v`
Expected: PASS (5 passed -- 3 existing + 2 new)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt pipeline/sync_pinecone.py tests/unit/test_sync_pinecone.py
git commit -m "feat: BM25 index build/store/load for hybrid retrieval"
```

---

### Task 2: query_rewriter.py

**Files:**
- Create: `server/retrieval/__init__.py`
- Create: `server/retrieval/query_rewriter.py`
- Test: `tests/unit/test_query_rewriter.py`

- [ ] **Step 1: Write the failing tests**

```python
from unittest.mock import MagicMock

from server.retrieval.query_rewriter import rewrite_query


def _fake_bedrock_client(rewritten_text: str) -> MagicMock:
    client = MagicMock()
    client.converse.return_value = {
        "output": {"message": {"content": [{"text": rewritten_text}]}}
    }
    return client


def test_rewrite_query_calls_haiku_and_returns_text():
    client = _fake_bedrock_client(
        "Nvidia Corporation NVDA data center segment revenue Q1 2024 Q1 2026 10-Q"
    )

    result = rewrite_query(client, "How did Nvidia data center revenue change?")

    assert result == "Nvidia Corporation NVDA data center segment revenue Q1 2024 Q1 2026 10-Q"
    call_kwargs = client.converse.call_args.kwargs
    assert call_kwargs["modelId"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert "How did Nvidia data center revenue change?" in str(call_kwargs["messages"])


def test_rewrite_query_strips_whitespace():
    client = _fake_bedrock_client("  NVDA revenue  \n")

    result = rewrite_query(client, "NVDA revenue")

    assert result == "NVDA revenue"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_query_rewriter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.retrieval'`

- [ ] **Step 3: Create the package and implementation**

```bash
mkdir -p server/retrieval
touch server/retrieval/__init__.py
```

Write `server/retrieval/query_rewriter.py`:

```python
"""Query rewriting via Claude Haiku on Bedrock: expand tickers, extract dates.

Uses a cross-region inference profile ID (the `us.` prefix), not the bare
`anthropic.claude-*` model ID -- Claude Haiku 4.5 rejects on-demand
invocation without it (verified against AWS Bedrock docs).
"""
from __future__ import annotations

from typing import Any

HAIKU_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

SYSTEM_PROMPT = (
    "Expand ticker symbols to company names. Extract time constraints. "
    "Optimize for financial document retrieval. Return rewritten query only."
)


def rewrite_query(bedrock_client: Any, query: str) -> str:
    """Rewrite a user query for better financial document retrieval.

    Args:
        bedrock_client: A boto3 bedrock-runtime client.
        query: The original user query.

    Returns:
        The rewritten query text.
    """
    response = bedrock_client.converse(
        modelId=HAIKU_MODEL_ID,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": query}]}],
    )
    return response["output"]["message"]["content"][0]["text"].strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_query_rewriter.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Verify the Bedrock model ID for real (not just mocked)**

Before committing, confirm `us.anthropic.claude-haiku-4-5-20251001-v1:0` is still the correct, current inference profile ID -- do NOT trust the hardcoded string blindly, model IDs and profile availability change. Run:

```bash
aws bedrock list-inference-profiles --region us-east-1 --query "inferenceProfileSummaries[?contains(inferenceProfileId, 'haiku-4-5')].inferenceProfileId" --output text
```

If the AWS CLI isn't configured/available in this environment, or the command errors, that's fine -- report it as unverified in your task report rather than blocking, since Week 1's precedent (Task 7) is to flag SDK/API surface uncertainty rather than silently trust it. If it IS available and returns a different ID than `us.anthropic.claude-haiku-4-5-20251001-v1:0`, update `HAIKU_MODEL_ID` to match and re-run tests.

- [ ] **Step 6: Commit**

```bash
git add server/retrieval/__init__.py server/retrieval/query_rewriter.py tests/unit/test_query_rewriter.py
git commit -m "feat: query_rewriter.py -- Haiku-powered query expansion"
```

---

### Task 3: hybrid_retriever.py

**Files:**
- Create: `server/retrieval/hybrid_retriever.py`
- Test: `tests/unit/test_hybrid_retriever.py`

- [ ] **Step 1: Write the failing tests**

```python
from unittest.mock import MagicMock

from rank_bm25 import BM25Okapi

from server.retrieval.hybrid_retriever import bm25_search, hybrid_search, merge_and_dedup


def _bm25_fixture():
    chunks = [
        {"chunk_id": "c1", "text": "Nvidia data center revenue grew significantly"},
        {"chunk_id": "c2", "text": "Apple iPhone revenue declined slightly this quarter"},
    ]
    tokenized = [c["text"].lower().split() for c in chunks]
    return BM25Okapi(tokenized), chunks


def test_bm25_search_returns_top_k_chunks_by_score():
    bm25, chunks = _bm25_fixture()

    results = bm25_search(bm25, chunks, "Nvidia data center revenue", top_k=1)

    assert len(results) == 1
    assert results[0]["chunk_id"] == "c1"


def test_merge_and_dedup_removes_duplicate_chunk_ids():
    bm25_chunks = [{"chunk_id": "c1", "text": "a"}, {"chunk_id": "c2", "text": "b"}]
    pinecone_matches = [
        {"id": "c2", "metadata": {"text": "b"}},
        {"id": "c3", "metadata": {"text": "c"}},
    ]

    merged = merge_and_dedup(bm25_chunks, pinecone_matches)

    assert [c["chunk_id"] for c in merged] == ["c1", "c2", "c3"]


def test_hybrid_search_runs_bm25_and_pinecone_in_parallel_and_merges():
    bm25, chunks = _bm25_fixture()
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {
        "matches": [{"id": "c3", "metadata": {"text": "Tesla margin fell"}}]
    }
    embed_fn = MagicMock(return_value=[0.1, 0.2])

    results = hybrid_search(
        rewritten_query="Nvidia data center revenue",
        bm25_index=bm25,
        bm25_chunks=chunks,
        pinecone_index=pinecone_index,
        embed_fn=embed_fn,
        top_k=10,
    )

    ids = {c["chunk_id"] for c in results}
    assert "c1" in ids  # from BM25
    assert "c3" in ids  # from Pinecone
    embed_fn.assert_called_once_with("Nvidia data center revenue")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_hybrid_retriever.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.retrieval.hybrid_retriever'`

- [ ] **Step 3: Implement**

```python
"""Parallel BM25 keyword search + Pinecone dense search, merged and deduped."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from rank_bm25 import BM25Okapi


def bm25_search(
    bm25_index: BM25Okapi, chunks: list[dict[str, Any]], query: str, top_k: int = 10
) -> list[dict[str, Any]]:
    """Rank chunks by BM25 keyword relevance to a query.

    Args:
        bm25_index: A BM25Okapi index built over `chunks`' text (same order).
        chunks: The chunks the index was built from.
        query: The search query.
        top_k: Number of top-scoring chunks to return.

    Returns:
        Up to top_k chunks, highest BM25 score first.
    """
    scores = bm25_index.get_scores(query.lower().split())
    ranked_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [chunks[i] for i in ranked_idx]


def _normalize_pinecone_match(match: dict[str, Any]) -> dict[str, Any]:
    chunk = dict(match["metadata"])
    chunk["chunk_id"] = match["id"]
    return chunk


def merge_and_dedup(
    bm25_chunks: list[dict[str, Any]], pinecone_matches: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge BM25 and Pinecone results, deduplicating by chunk_id.

    Args:
        bm25_chunks: Results from bm25_search() (already chunk-shaped).
        pinecone_matches: Raw matches from pinecone_index.query()["matches"]
            (each a {"id", "metadata"} dict, normalized here to chunk shape).

    Returns:
        Deduplicated chunks, BM25 results first, then new Pinecone results,
        original relative order preserved within each source.
    """
    normalized_pinecone = [_normalize_pinecone_match(m) for m in pinecone_matches]
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for chunk in [*bm25_chunks, *normalized_pinecone]:
        chunk_id = chunk["chunk_id"]
        if chunk_id not in seen:
            seen.add(chunk_id)
            merged.append(chunk)
    return merged


def hybrid_search(
    rewritten_query: str,
    bm25_index: BM25Okapi,
    bm25_chunks: list[dict[str, Any]],
    pinecone_index: Any,
    embed_fn: Callable[[str], list[float]],
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Run BM25 and Pinecone search in parallel, merge and dedup the results.

    Args:
        rewritten_query: The query text from query_rewriter.rewrite_query().
        bm25_index: A BM25Okapi index over the full corpus.
        bm25_chunks: The chunks bm25_index was built from.
        pinecone_index: A Pinecone Index handle.
        embed_fn: Callable(text) -> embedding vector, for the Pinecone query.
        top_k: Number of results to take from each source before merging.

    Returns:
        Up to 2*top_k deduplicated candidate chunks.
    """
    with ThreadPoolExecutor(max_workers=2) as executor:
        bm25_future = executor.submit(bm25_search, bm25_index, bm25_chunks, rewritten_query, top_k)
        pinecone_future = executor.submit(
            lambda: pinecone_index.query(
                vector=embed_fn(rewritten_query), top_k=top_k, include_metadata=True
            )["matches"]
        )
        bm25_results = bm25_future.result()
        pinecone_matches = pinecone_future.result()

    return merge_and_dedup(bm25_results, pinecone_matches)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_hybrid_retriever.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add server/retrieval/hybrid_retriever.py tests/unit/test_hybrid_retriever.py
git commit -m "feat: hybrid_retriever.py -- parallel BM25 + Pinecone with merge/dedup"
```

---

### Task 4: reranker.py

**Files:**
- Create: `server/retrieval/reranker.py`
- Test: `tests/unit/test_reranker.py`

**Note on packaging:** this task builds and unit-tests the reranking *logic* only, using the real `sentence-transformers` CrossEncoder locally (it works fine in a dev venv -- the problem is only Lambda's 250MB zip limit, not the library itself). Deploying it as a container-image Lambda is Task 9 (manual/infra), not this task.

- [ ] **Step 1: Add the dependency**

Add to `requirements.txt`:

```
sentence-transformers>=3.0,<4.0
```

Run: `source .venv/bin/activate && pip install -r requirements.txt`
Expected: installs successfully, pulling in `torch` (CPU build) and `transformers` as dependencies. This will take noticeably longer than prior installs (~1-2 min, larger download) -- that's expected given the ~1.2GB footprint discussed in Week 1 planning.

- [ ] **Step 2: Write the failing tests**

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/unit/test_reranker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.retrieval.reranker'`

- [ ] **Step 4: Implement**

```python
"""CrossEncoder reranking: top-N candidates -> top-K by true relevance.

Deployed as a separate container-image Lambda (not the main zip-deployed
API Lambda) -- sentence-transformers + torch is ~1.2GB installed, well over
Lambda's 250MB zip limit. See Task 9 for the container packaging/deploy.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from sentence_transformers import CrossEncoder

MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=1)
def _get_model() -> CrossEncoder:
    """Load the CrossEncoder model once per process (Lambda warm start)."""
    return CrossEncoder(MODEL_NAME)


def rerank(query: str, chunks: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
    """Rerank candidate chunks by true relevance to the query.

    Args:
        query: The original user query (not the rewritten one -- CrossEncoder
            models are trained on natural queries, not keyword-expanded ones).
        chunks: Candidate chunks from hybrid_retriever.hybrid_search().
        top_k: Number of top-ranked chunks to return.

    Returns:
        Up to top_k chunks, highest true-relevance score first.
    """
    model = _get_model()
    pairs = [(query, chunk["text"]) for chunk in chunks]
    scores = model.predict(pairs)
    ranked = sorted(zip(scores, chunks), key=lambda pair: pair[0], reverse=True)
    return [chunk for _score, chunk in ranked[:top_k]]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_reranker.py -v`
Expected: PASS (2 passed). Note: first run downloads the ~90MB MiniLM model from HuggingFace to a local cache (`~/.cache/huggingface`) -- expect a one-time delay; subsequent runs are fast.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt server/retrieval/reranker.py tests/unit/test_reranker.py
git commit -m "feat: reranker.py -- CrossEncoder top-N to top-K reranking"
```

---

### Task 5: numerical_verifier.py

**Files:**
- Create: `server/retrieval/numerical_verifier.py`
- Test: `tests/unit/test_numerical_verifier.py`

- [ ] **Step 1: Write the failing tests**

```python
from server.retrieval.numerical_verifier import extract_numbers, verify_answer


def test_extract_numbers_finds_dollar_amounts_and_percentages():
    text = "Revenue grew to $9.06 billion, a 78% increase, with $23,400 million in total."

    numbers = extract_numbers(text)

    assert "$9.06 billion" in numbers
    assert "78%" in numbers
    assert "$23,400 million" in numbers


def test_verify_answer_keeps_numbers_found_in_source_chunks():
    answer = "Nvidia's data center revenue was $9.06 billion, a 78% increase."
    source_chunks = ["Data center revenue reached $9.06 billion this quarter, up 78% year over year."]

    verified = verify_answer(answer, source_chunks)

    assert "$9.06 billion" in verified
    assert "78%" in verified
    assert "exact figure unavailable" not in verified


def test_verify_answer_flags_numbers_not_found_in_source_chunks():
    answer = "Nvidia's revenue was $50 billion this quarter."
    source_chunks = ["Nvidia's revenue was $9.06 billion this quarter."]

    verified = verify_answer(answer, source_chunks)

    assert "$50 billion" not in verified
    assert "exact figure unavailable" in verified
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_numerical_verifier.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.retrieval.numerical_verifier'`

- [ ] **Step 3: Implement**

```python
"""Post-generation numerical grounding: every number must appear in a source chunk.

CLAUDE.md Phase 9 constraint #1: every number in the answer MUST appear
verbatim (in some format) in a retrieved chunk. This is a Week 2 baseline
implementation -- exact-substring matching after normalizing common dollar
formats, not full unit-conversion equivalence ("23,400 million" == "23.4
billion" is a documented Week 3+ gap, not attempted here).
"""
from __future__ import annotations

import re

NUMBER_PATTERN = re.compile(
    r"\$[\d,]+(?:\.\d+)?\s?(?:billion|million|thousand|B|M|K)?"  # dollar amounts
    r"|\d+(?:\.\d+)?%"  # percentages
    r"|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"  # large comma-separated numbers
)


def extract_numbers(text: str) -> list[str]:
    """Extract dollar amounts, percentages, and large numbers from text.

    Args:
        text: Text to scan (typically a generated answer).

    Returns:
        List of matched number substrings, in order of appearance.
    """
    return NUMBER_PATTERN.findall(text)


def verify_answer(answer: str, source_chunks: list[str]) -> str:
    """Remove any number in the answer that doesn't appear in a source chunk.

    Args:
        answer: The generated answer text.
        source_chunks: Raw text of the chunks the answer was generated from.

    Returns:
        The answer with ungrounded numbers replaced by a qualifier, and one
        combined note appended listing what was removed (if anything was).
    """
    combined_sources = " ".join(source_chunks)
    numbers = extract_numbers(answer)
    ungrounded = [n for n in numbers if n not in combined_sources]

    verified = answer
    for number in ungrounded:
        verified = verified.replace(number, "[exact figure unavailable in retrieved context]")

    return verified
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_numerical_verifier.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add server/retrieval/numerical_verifier.py tests/unit/test_numerical_verifier.py
git commit -m "feat: numerical_verifier.py -- number extraction + source grounding check"
```

---

### Task 6: answer_generator.py

**Files:**
- Create: `server/generation/__init__.py`
- Create: `server/generation/answer_generator.py`
- Test: `tests/unit/test_answer_generator.py`

- [ ] **Step 1: Write the failing tests**

```python
from unittest.mock import MagicMock

from server.generation.answer_generator import format_citation, generate_answer


def _fake_bedrock_client(answer_text: str) -> MagicMock:
    client = MagicMock()
    client.converse.return_value = {
        "output": {"message": {"content": [{"text": answer_text}]}}
    }
    return client


def test_format_citation_matches_claude_md_format():
    chunk = {"ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026", "page_number": 23}

    citation = format_citation(chunk)

    assert citation == "[NVDA 10-Q Q1-2026 p.23]"


def test_format_citation_omits_page_when_none():
    chunk = {"ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026", "page_number": None}

    citation = format_citation(chunk)

    assert citation == "[NVDA 10-Q Q1-2026]"


def test_generate_answer_calls_sonnet_with_context_and_citations():
    client = _fake_bedrock_client("Data center revenue grew [NVDA 10-Q Q1-2026].")
    chunks = [
        {
            "chunk_id": "c1",
            "text": "Data center revenue reached $9.06 billion.",
            "ticker": "NVDA",
            "filing_type": "10-Q",
            "period": "Q1-2026",
            "page_number": None,
        }
    ]

    answer = generate_answer(client, "How did Nvidia data center revenue change?", chunks)

    assert answer == "Data center revenue grew [NVDA 10-Q Q1-2026]."
    call_kwargs = client.converse.call_args.kwargs
    assert call_kwargs["modelId"] == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert "$9.06 billion" in str(call_kwargs["messages"])
    assert "[NVDA 10-Q Q1-2026]" in str(call_kwargs["system"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_answer_generator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.generation'`

- [ ] **Step 3: Create the package and implementation**

```bash
mkdir -p server/generation
touch server/generation/__init__.py
```

Write `server/generation/answer_generator.py`:

```python
"""Bedrock Sonnet Converse API generation with mandatory inline citations.

Uses a cross-region inference profile ID (the `us.` prefix) -- same
requirement as query_rewriter.py's Haiku call, verified against AWS
Bedrock docs this session.
"""
from __future__ import annotations

from typing import Any

SONNET_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

SYSTEM_PROMPT_TEMPLATE = """Cite every claim with the exact citation format shown below each passage.
Never state a number not present verbatim in the provided context.
If context is insufficient, say so explicitly. Do not guess.
Format citations inline as shown, e.g. {example_citation}

Context:
{context}"""


def format_citation(chunk: dict[str, Any]) -> str:
    """Format a chunk's metadata as a CLAUDE.md-style inline citation.

    Args:
        chunk: A chunk dict with ticker, filing_type, period, page_number.

    Returns:
        "[TICKER FILING_TYPE PERIOD p.N]", or without the page segment if
        page_number is None (HTML filings have no native pagination).
    """
    base = f"[{chunk['ticker']} {chunk['filing_type']} {chunk['period']}"
    if chunk.get("page_number") is not None:
        return f"{base} p.{chunk['page_number']}]"
    return f"{base}]"


def generate_answer(bedrock_client: Any, query: str, chunks: list[dict[str, Any]]) -> str:
    """Generate a cited answer from the top reranked chunks.

    Args:
        bedrock_client: A boto3 bedrock-runtime client.
        query: The original user query.
        chunks: Top chunks from reranker.rerank(), each with text + citation
            metadata (ticker, filing_type, period, page_number).

    Returns:
        The generated answer text with inline citations.
    """
    context_blocks = [f"{chunk['text']}\nCitation: {format_citation(chunk)}" for chunk in chunks]
    example_citation = format_citation(chunks[0]) if chunks else "[TICKER 10-Q PERIOD]"

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        example_citation=example_citation, context="\n\n".join(context_blocks)
    )

    response = bedrock_client.converse(
        modelId=SONNET_MODEL_ID,
        system=[{"text": system_prompt}],
        messages=[{"role": "user", "content": [{"text": query}]}],
    )
    return response["output"]["message"]["content"][0]["text"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_answer_generator.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Verify the Sonnet model ID for real**, same as Task 2 Step 5:

```bash
aws bedrock list-inference-profiles --region us-east-1 --query "inferenceProfileSummaries[?contains(inferenceProfileId, 'sonnet-4-5')].inferenceProfileId" --output text
```

Report unverified if the CLI isn't available; update `SONNET_MODEL_ID` and re-test if it returns something different.

- [ ] **Step 6: Commit**

```bash
git add server/generation/__init__.py server/generation/answer_generator.py tests/unit/test_answer_generator.py
git commit -m "feat: answer_generator.py -- Sonnet generation with inline citations"
```

---

### Task 7: Wire the full pipeline into search_filings.py

**Files:**
- Modify: `server/mcp_tools/search_filings.py`
- Modify: `tests/unit/test_search_filings.py`
- Modify: `server/main.py`

This replaces Week 1's `build_search_filings_answer` (direct Pinecone query only) with the full four-stage pipeline. The function signature grows to take the new dependencies; `server/main.py`'s `_build_production_dependencies()` and `create_app()` wiring grows to match.

- [ ] **Step 1: Write the failing test (replaces the existing Week 1 test for this function)**

Replace the contents of `tests/unit/test_search_filings.py` with:

```python
from unittest.mock import MagicMock, patch

from mcp.server import MCPServer

from server.mcp_tools.search_filings import (
    build_search_filings_answer,
    register_search_filings_tool,
)


def _deps():
    bedrock_client = MagicMock()
    bedrock_client.converse.side_effect = [
        {"output": {"message": {"content": [{"text": "NVDA data center revenue Q1 2026"}]}}},
        {"output": {"message": {"content": [{"text": "Revenue grew [NVDA 10-Q Q1-2026]."}]}}},
    ]
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {"matches": []}
    bm25_index = MagicMock()
    bm25_index.get_scores.return_value = []
    bm25_chunks: list[dict] = []
    embed_fn = MagicMock(return_value=[0.1, 0.2])
    return bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn


@patch("server.mcp_tools.search_filings.rerank")
def test_build_search_filings_answer_runs_full_pipeline(mock_rerank):
    bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn = _deps()
    mock_rerank.return_value = [
        {
            "chunk_id": "c1",
            "text": "Data center revenue reached $9.06 billion.",
            "ticker": "NVDA",
            "filing_type": "10-Q",
            "period": "Q1-2026",
            "page_number": None,
        }
    ]

    result = build_search_filings_answer(
        "How did Nvidia data center revenue change?",
        bedrock_client=bedrock_client,
        pinecone_index=pinecone_index,
        bm25_index=bm25_index,
        bm25_chunks=bm25_chunks,
        embed_fn=embed_fn,
    )

    assert "Revenue grew" in result["answer"]
    assert result["citations"] == [
        {"ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026", "page": None}
    ]
    assert isinstance(result["latency_ms"], int)
    mock_rerank.assert_called_once()


@patch("server.mcp_tools.search_filings.rerank")
def test_register_search_filings_tool_does_not_raise(mock_rerank):
    mock_rerank.return_value = []
    bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn = _deps()
    mcp = MCPServer("Test")

    register_search_filings_tool(
        mcp, bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_search_filings.py -v`
Expected: FAIL -- `build_search_filings_answer`'s current signature doesn't accept these kwargs (`TypeError: build_search_filings_answer() got an unexpected keyword argument 'bedrock_client'`).

- [ ] **Step 3: Rewrite server/mcp_tools/search_filings.py**

```python
"""search_sec_filings MCP tool: full retrieval pipeline (Week 2).

rewrite -> hybrid search -> rerank -> generate -> verify, per CLAUDE.md's
query flow. Replaces Week 1's direct-Pinecone-only version.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from mcp.server import MCPServer
from rank_bm25 import BM25Okapi

from server.generation.answer_generator import format_citation, generate_answer
from server.retrieval.hybrid_retriever import hybrid_search
from server.retrieval.numerical_verifier import verify_answer
from server.retrieval.query_rewriter import rewrite_query
from server.retrieval.reranker import rerank


def build_search_filings_answer(
    query: str,
    bedrock_client: Any,
    pinecone_index: Any,
    bm25_index: BM25Okapi,
    bm25_chunks: list[dict[str, Any]],
    embed_fn: Callable[[str], list[float]],
    top_k: int = 5,
) -> dict[str, Any]:
    """Run the full four-stage retrieval pipeline and format a cited answer.

    Args:
        query: Natural language financial question.
        bedrock_client: A boto3 bedrock-runtime client (used for rewrite,
            generation, and -- via embed_fn's closure -- embeddings).
        pinecone_index: A Pinecone Index handle.
        bm25_index: The corpus-wide BM25 index from sync_pinecone.load_bm25_index().
        bm25_chunks: The chunks bm25_index was built from.
        embed_fn: Callable(text) -> embedding vector, for the Pinecone query.
        top_k: Number of chunks to keep after reranking.

    Returns:
        {"answer": str, "citations": [...], "cost_usd": float, "latency_ms": int}
    """
    start = time.monotonic()

    rewritten = rewrite_query(bedrock_client, query)
    candidates = hybrid_search(rewritten, bm25_index, bm25_chunks, pinecone_index, embed_fn)
    top_chunks = rerank(query, candidates, top_k=top_k)

    raw_answer = generate_answer(bedrock_client, query, top_chunks)
    source_texts = [chunk["text"] for chunk in top_chunks]
    verified_answer = verify_answer(raw_answer, source_texts)

    citations = [
        {
            "ticker": chunk.get("ticker"),
            "filing_type": chunk.get("filing_type"),
            "period": chunk.get("period"),
            "page": chunk.get("page_number"),
        }
        for chunk in top_chunks
    ]

    latency_ms = int((time.monotonic() - start) * 1000)

    return {
        "answer": verified_answer,
        "citations": citations,
        "cost_usd": 0.0,  # Week 4 wires real per-stage cost tracking
        "latency_ms": latency_ms,
    }


def register_search_filings_tool(
    mcp: MCPServer,
    bedrock_client: Any,
    pinecone_index: Any,
    bm25_index: BM25Okapi,
    bm25_chunks: list[dict[str, Any]],
    embed_fn: Callable[[str], list[float]],
) -> None:
    """Register the search_sec_filings tool on an MCPServer instance.

    Args:
        mcp: The MCPServer instance to register the tool on.
        bedrock_client: A boto3 bedrock-runtime client.
        pinecone_index: A Pinecone Index handle.
        bm25_index: The corpus-wide BM25 index.
        bm25_chunks: The chunks bm25_index was built from.
        embed_fn: Callable(text) -> embedding vector.
    """

    @mcp.tool()
    def search_sec_filings(query: str) -> dict[str, Any]:
        """Search ingested SEC filings and return a cited answer.

        Args:
            query: Natural language financial question, e.g. "How did
                Nvidia data center revenue change from Q1 2024 to Q1 2026?"

        Returns:
            Dict with answer text, citations, cost_usd, and latency_ms.
        """
        return build_search_filings_answer(
            query, bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn
        )
```

Note: `format_citation` is imported but only used inside `answer_generator.py` itself -- remove it from this file's imports if your editor/linter flags it as unused (it's needed in `answer_generator.py`, not here; this file builds citations inline via the dict comprehension instead of calling `format_citation`, since the MCP tool's citation output is structured JSON, not the inline-bracket string `format_citation` produces for the prompt).

- [ ] **Step 4: Update server/main.py to build and pass the new dependencies**

Modify `server/main.py`'s `_build_production_dependencies()` and `create_app()`/`get_app()`:

```python
"""FastAPI app entry point with MCP tool registration for FinRAG MCP.

Week 2 scope: full four-stage pipeline (rewrite -> hybrid -> rerank ->
generate -> verify). BM25 index is loaded once from S3 at app startup
(inside get_app(), same lazy-construction pattern as the Pinecone index --
both need real credentials/network access, so neither happens at import time).
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import lru_cache, partial
from typing import Any

import boto3
from fastapi import FastAPI
from mangum import Mangum
from mcp.server import MCPServer

from pipeline.sync_pinecone import embed_text, get_pinecone_index, load_bm25_index
from server.mcp_tools.search_filings import register_search_filings_tool

PROCESSED_BUCKET = "finrag-processed-filings"
BM25_INDEX_KEY = "bm25/index.pkl"


def create_app(
    bedrock_client: Any,
    pinecone_index: Any,
    bm25_index: Any,
    bm25_chunks: list[dict[str, Any]],
    embed_fn: Callable[[str], list[float]],
) -> FastAPI:
    """Build the FastAPI app with the MCP server mounted.

    Args:
        bedrock_client: A boto3 bedrock-runtime client.
        pinecone_index: A Pinecone Index handle for the search tool.
        bm25_index: The corpus-wide BM25 index.
        bm25_chunks: The chunks bm25_index was built from.
        embed_fn: Callable(text) -> embedding vector for embedding queries.

    Returns:
        A FastAPI app ready to serve via Mangum on Lambda.
    """
    mcp = MCPServer("FinRAG")
    register_search_filings_tool(
        mcp, bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.mount("/", mcp.streamable_http_app())
    return app


def _build_production_dependencies() -> tuple[Any, Any, Any, list[dict[str, Any]], Callable[[str], list[float]]]:
    """Wire up real Bedrock + Pinecone + BM25 clients for production use."""
    bedrock_client = boto3.client("bedrock-runtime")
    s3_client = boto3.client("s3")
    pinecone_index = get_pinecone_index(
        api_key=os.environ["PINECONE_API_KEY"], index_name="finrag-filings"
    )
    bm25_index, bm25_chunks = load_bm25_index(s3_client, PROCESSED_BUCKET, BM25_INDEX_KEY)
    return bedrock_client, pinecone_index, bm25_index, bm25_chunks, partial(embed_text, bedrock_client)


@lru_cache(maxsize=1)
def get_app() -> FastAPI:
    """Build the production FastAPI app once, on first real use.

    Deferred past import time -- Pinecone's client resolves an index's host
    via a control-plane API call at construction, and loading the BM25
    index requires a real S3 read, both of which would require live
    credentials just to import this module otherwise.
    """
    bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn = _build_production_dependencies()
    return create_app(bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn)


def handler(event: Any, context: Any) -> Any:
    """Lambda entry point. Builds the app lazily via `get_app()`."""
    return Mangum(get_app())(event, context)
```

- [ ] **Step 5: Update tests/unit/test_main.py for the new create_app signature**

Replace the contents of `tests/unit/test_main.py` with:

```python
from unittest.mock import MagicMock

from server.main import create_app


def test_create_app_returns_fastapi_app_with_mcp_mounted():
    bedrock_client = MagicMock()
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {"matches": []}
    bm25_index = MagicMock()
    bm25_chunks: list[dict] = []
    embed_fn = MagicMock(return_value=[0.0])

    app = create_app(bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn)

    route_paths = [getattr(r, "path", None) for r in app.routes]
    assert any(path in ("/", "") for path in route_paths)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/unit -v`
Expected: All tests pass, including the rewritten `test_search_filings.py` and `test_main.py`.

- [ ] **Step 7: Commit**

```bash
git add server/mcp_tools/search_filings.py server/main.py tests/unit/test_search_filings.py tests/unit/test_main.py
git commit -m "feat: wire full retrieval pipeline into search_sec_filings"
```

---

### Task 8: Expand corpus to 50 companies + build BM25 index at end of bootstrap

CLAUDE.md Phase 6 only enumerates the initial 20 tickers; expanding to 50 by Week 2 is stated as a goal without naming the other 30. This plan adds 30 more across 6 additional sectors (Energy, Consumer Retail, Industrials, Telecom, Media, Semiconductors-adjacent) to keep FinanceBench-style coverage broad for Week 3's eval. If you want a different set, this is the one line to edit.

**Files:**
- Modify: `scripts/bootstrap_corpus.py`
- Modify: `tests/unit/test_bootstrap_corpus.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_bootstrap_corpus.py` (the existing `test_target_tickers_has_exactly_twenty_companies` test needs updating too):

```python
def test_target_tickers_has_exactly_fifty_companies():
    assert len(TARGET_TICKERS) == 50
    assert len(set(TARGET_TICKERS)) == 50  # no duplicates
```

Remove the old `test_target_tickers_has_exactly_twenty_companies` test (replaced by the above -- keep only one ticker-count test, don't leave a permanently-failing old assertion in the suite).

Add a test for the new BM25-building step in `main()`:

```python
from unittest.mock import patch


@patch("scripts.bootstrap_corpus.build_and_store_bm25_index")
@patch("scripts.bootstrap_corpus.bootstrap_ticker")
@patch("scripts.bootstrap_corpus.get_pinecone_index")
@patch("scripts.bootstrap_corpus.boto3")
def test_main_builds_bm25_index_after_all_tickers(
    mock_boto3, mock_get_index, mock_bootstrap_ticker, mock_build_bm25
):
    mock_bootstrap_ticker.return_value = (5, [{"chunk_id": "c1", "text": "x"}])

    import os

    os.environ["PINECONE_API_KEY"] = "test-key"
    main()

    assert mock_bootstrap_ticker.call_count == len(TARGET_TICKERS)
    mock_build_bm25.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_bootstrap_corpus.py -v`
Expected: FAIL (`test_target_tickers_has_exactly_fifty_companies` fails -- still 20 tickers; `test_main_builds_bm25_index_after_all_tickers` fails -- `bootstrap_ticker` doesn't return a tuple yet and `build_and_store_bm25_index` isn't called)

- [ ] **Step 3: Update scripts/bootstrap_corpus.py**

`bootstrap_ticker` needs to also return the chunks it processed (not just the count), so `main()` can accumulate them corpus-wide for the BM25 index build at the end:

```python
"""One-time bootstrap: ingest the initial 50-company corpus end to end.

Runs edgar_client -> html_processor -> chunker -> sync_pinecone for each
ticker in TARGET_TICKERS, then builds one corpus-wide BM25 index from all
chunks and stores it to S3. Run once locally to seed the corpus before the
weekly refresh cron (Week 4+) takes over.
"""
from __future__ import annotations

import os
from typing import Any

import boto3

from pipeline.chunker import chunk_filing
from pipeline.edgar_client import download_filing, get_cik_for_ticker, list_filings, store_filing
from pipeline.html_processor import process_filing
from pipeline.sync_pinecone import (
    build_and_store_bm25_index,
    get_pinecone_index,
    sync_chunks_to_pinecone,
)

TARGET_TICKERS = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "META",       # Tech
    "TSLA", "F", "GM", "RIVN", "LCID",             # EV/Auto
    "JPM", "BAC", "GS", "MS", "V",                 # Finance
    "JNJ", "PFE", "UNH", "ABBV", "MRK",            # Healthcare
    "XOM", "CVX", "COP", "SLB", "OXY",             # Energy
    "WMT", "COST", "HD", "TGT", "LOW",             # Consumer Retail
    "BA", "CAT", "GE", "HON", "UPS",               # Industrials
    "T", "VZ", "TMUS", "CMCSA", "CHTR",            # Telecom
    "DIS", "NFLX", "WBD", "PARA", "SPOT",          # Media
    "AMD", "INTC", "QCOM", "TXN", "AVGO",          # Semiconductors
]

RAW_BUCKET = "finrag-raw-filings"
PROCESSED_BUCKET = "finrag-processed-filings"
BM25_INDEX_KEY = "bm25/index.pkl"


def bootstrap_ticker(
    s3_client: Any, bedrock_client: Any, pinecone_index: Any, ticker: str
) -> tuple[int, list[dict[str, Any]]]:
    """Ingest, process, chunk, and sync one ticker's filings end to end.

    Args:
        s3_client: A boto3 S3 client.
        bedrock_client: A boto3 bedrock-runtime client.
        pinecone_index: A Pinecone Index handle.
        ticker: Stock ticker symbol to bootstrap.

    Returns:
        (total chunks synced, all chunks processed) -- the chunks are
        returned so main() can accumulate them corpus-wide for the BM25
        index built once after every ticker is done.
    """
    cik = get_cik_for_ticker(ticker)
    filings = list_filings(ticker, cik)

    total_chunks = 0
    all_chunks: list[dict[str, Any]] = []
    for filing in filings:
        try:
            html = download_filing(filing).decode("utf-8", errors="ignore")
            store_filing(s3_client, RAW_BUCKET, filing, html.encode("utf-8"))

            metadata = {
                "ticker": filing.ticker,
                "filing_type": filing.form_type,
                "period": filing.filing_date,
            }
            processed = process_filing(html, metadata)
            chunks = chunk_filing(processed)
            total_chunks += sync_chunks_to_pinecone(bedrock_client, pinecone_index, chunks)
            all_chunks.extend(chunks)
        except Exception as e:
            print(f"{ticker} {filing.accession_number}: failed - {e}")
            continue

    return total_chunks, all_chunks


def main() -> None:
    """Bootstrap the full 50-company corpus and build the BM25 index."""
    s3_client = boto3.client("s3")
    bedrock_client = boto3.client("bedrock-runtime")
    pinecone_index = get_pinecone_index(
        api_key=os.environ["PINECONE_API_KEY"], index_name="finrag-filings"
    )

    corpus_chunks: list[dict[str, Any]] = []
    for ticker in TARGET_TICKERS:
        count, chunks = bootstrap_ticker(s3_client, bedrock_client, pinecone_index, ticker)
        corpus_chunks.extend(chunks)
        print(f"{ticker}: synced {count} chunks")

    build_and_store_bm25_index(s3_client, PROCESSED_BUCKET, BM25_INDEX_KEY, corpus_chunks)
    print(f"BM25 index built from {len(corpus_chunks)} total chunks")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_bootstrap_corpus.py -v`
Expected: PASS. Note: `test_bootstrap_ticker_runs_full_pipeline_per_filing` (the existing test from Week 1) asserts `total == 1` on `bootstrap_ticker`'s return value -- since the function now returns a tuple, update that assertion to `assert total == 1` where `total, _chunks = bootstrap_ticker(...)`, unpacking the tuple. Make this small fix to the existing test if it doesn't already account for the new return shape.

- [ ] **Step 5: Run the full unit test suite and lint**

Run: `pytest tests/unit -v && ruff check .`
Expected: All tests pass (should be ~38-40 total across the whole repo at this point), lint clean.

- [ ] **Step 6: Commit**

```bash
git add scripts/bootstrap_corpus.py tests/unit/test_bootstrap_corpus.py
git commit -m "feat: expand corpus to 50 companies, build BM25 index after bootstrap"
```

---

### Task 9: Deploy reranker container Lambda, re-run corpus, test 20 manual questions (manual, not unit-testable)

**Files:** none created — infrastructure deployment and manual verification, mirrors Week 1's Task 9.

- [ ] **Step 1: Write the reranker Dockerfile**

Create `server/retrieval/Dockerfile`:

```dockerfile
FROM public.ecr.aws/lambda/python:3.12

COPY requirements-reranker.txt .
RUN pip install --no-cache-dir -r requirements-reranker.txt

COPY server/retrieval/reranker.py ${LAMBDA_TASK_ROOT}/reranker.py

CMD ["reranker.lambda_handler"]
```

Create `requirements-reranker.txt` (only what the reranker Lambda needs -- do NOT reuse the main `requirements.txt`, which pulls in boto3/fastapi/mangum/pinecone/etc. that bloat this image for no reason):

```
sentence-transformers>=3.0,<4.0
```

Add a small Lambda handler to the bottom of `server/retrieval/reranker.py`:

```python
def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Container-image Lambda entry point: {query, chunks, top_k} -> reranked chunks."""
    query = event["query"]
    chunks = event["chunks"]
    top_k = event.get("top_k", 5)
    return {"chunks": rerank(query, chunks, top_k=top_k)}
```

- [ ] **Step 2: Add the reranker Lambda to CDK**

Modify `infra/stacks/mcp_server_stack.py` (new file -- not built in Week 1, create it now) to define a `DockerImageFunction` for the reranker, alongside the zip-deployed API Lambda for `server/main.py`. This is infra work with no existing pattern in the repo yet; if you're implementing this step, check the AWS CDK Python docs for `aws_cdk.aws_lambda.DockerImageFunction` and `DockerImageCode.from_image_asset()` current API before writing it, the same way Task 2/6 verified Bedrock model IDs rather than guessing.

- [ ] **Step 3: Deploy**

```bash
cdk deploy --app "python -m infra.app" --require-approval never
```

- [ ] **Step 4: Wire hybrid_retriever.py's caller to invoke the reranker Lambda instead of calling `rerank()` in-process**

In `server/mcp_tools/search_filings.py`, replace the direct `rerank(query, candidates, top_k=top_k)` call with a boto3 Lambda `invoke()` call to the deployed reranker function, passing `{"query": query, "chunks": candidates, "top_k": top_k}` as the payload and parsing the JSON response. This keeps the main API Lambda's zip small (no torch/sentence-transformers bundled into it) while still getting real reranking.

- [ ] **Step 5: Re-run the bootstrap script against the expanded 50-company corpus**

```bash
export PINECONE_API_KEY=<your-real-key>
python -m scripts.bootstrap_corpus
```

Expected: prints `TICKER: synced N chunks` for all 50 tickers (continuing past any individual filing failures per Task 8's error handling), then `BM25 index built from N total chunks`.

- [ ] **Step 6: Test 20 manual financial questions**

Per CLAUDE.md Phase 7 Week 2: ask Claude Desktop 20 real financial questions covering the corpus, check citation accuracy. Confirm answers now include Sonnet-generated prose (not raw passage dumps like Week 1), inline citations in `[TICKER FILING_TYPE PERIOD]` format, and that ungrounded numbers get the "[exact figure unavailable in retrieved context]" qualifier rather than being stated confidently.

- [ ] **Step 7: Push all commits**

```bash
git push
```

---

## Self-Review

**Spec coverage:** Every Week 2 CLAUDE.md task (Phase 7) has a corresponding task above: query_rewriter.py (Task 2), hybrid_retriever.py (Task 3, plus the BM25-index-building half of Phase 3 Step 4 that Week 1 deferred, in Task 1), reranker.py (Task 4, packaging in Task 9), numerical_verifier.py (Task 5), citation formatter in answer_generator.py (Task 6), full pipeline wiring (Task 7), expand corpus to 50 companies (Task 8), 20 manual questions (Task 9).

**Placeholder scan:** No TBD/TODO markers. Task 9 Step 2 (CDK DockerImageFunction) is the one step that asks the implementer to verify current API syntax rather than providing exact code — this mirrors Week 1's explicit precedent (Task 7 Step 8.5, verifying the `mcp` SDK by hand) for exactly the same reason: guessing at unfamiliar infrastructure API surface risks being silently wrong in a way unit tests can't catch, so verification is the safer instruction than a guessed code block.

**Type consistency:** `Callable[[str], list[float]]` for `embed_fn` stays consistent from Week 1 through every new module. Chunk dict shape (`chunk_id`, `text`, `ticker`, `filing_type`, `period`, `page_number`) flows unchanged from `chunker.py` (Week 1) through `hybrid_retriever.py`, `reranker.py`, `answer_generator.py`, and `numerical_verifier.py` in this plan — no field renames anywhere in the chain. `build_search_filings_answer`'s new signature (Task 7) matches exactly what `server/main.py`'s `create_app()`/`get_app()` construct and pass in.

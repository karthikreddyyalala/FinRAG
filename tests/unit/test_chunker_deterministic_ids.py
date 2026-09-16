"""TDD: chunk_id must be deterministic so re-ingestion is idempotent.

With random UUIDs, re-ingesting a filing writes a second copy of every chunk
to Pinecone under fresh ids, and BM25 ids never match Pinecone ids -- so
merge_and_dedup cannot dedup the two retrieval sources against each other.
"""
from pipeline.chunker import chunk_filing

PROCESSED = {
    "text_blocks": ["Revenue grew twelve percent year over year. " * 30],
    "tables": [{"headers": ["Segment", "Revenue"], "rows": [["Data Center", "$9.1B"]]}],
    "metadata": {"ticker": "NVDA", "filing_type": "10-Q", "period": "2026-01-30"},
}


def test_chunk_ids_are_stable_across_runs():
    """Chunking the same filing twice must produce identical chunk_ids."""
    first = [c["chunk_id"] for c in chunk_filing(PROCESSED)]
    second = [c["chunk_id"] for c in chunk_filing(PROCESSED)]

    assert first == second, "chunk_ids changed between identical runs -- re-ingest duplicates"


def test_different_content_gets_different_ids():
    """Distinct chunks must not collide."""
    ids = [c["chunk_id"] for c in chunk_filing(PROCESSED)]
    assert len(ids) == len(set(ids)), f"duplicate chunk_ids within one filing: {ids}"


def test_same_text_in_different_filings_gets_different_ids():
    """Identical boilerplate in two filings must stay addressable separately."""
    other = {**PROCESSED, "metadata": {**PROCESSED["metadata"], "ticker": "AMD"}}
    nvda = {c["chunk_id"] for c in chunk_filing(PROCESSED)}
    amd = {c["chunk_id"] for c in chunk_filing(other)}

    assert not (nvda & amd), "chunks from different tickers collided"

"""TDD: SQLite FTS5 keyword index, replacing the in-memory rank-bm25 pickle.

rank-bm25 did not survive the corpus reaching 164k chunks: building it
peaked at 7.5 GB (it needed a temporary EC2 box), loading it took 212 s, and
`text.lower().split()` left punctuation attached so "property," never
matched "property". FTS5 keeps genuine BM25 ranking (its built-in bm25()),
builds by streaming inserts, reads from disk instead of RAM, and tokenizes
properly -- which is what makes a Lambda cold start and a weekly rebuild
inside a Lambda possible at all.
"""
from unittest.mock import MagicMock

import botocore.exceptions
import pytest

from pipeline.sync_pinecone import (
    BM25_CHUNK_FIELDS,
    KeywordIndex,
    build_keyword_index,
    load_keyword_index,
)


def _chunk(cid, text, ticker="MMM"):
    return {
        "chunk_id": cid,
        "text": text,
        "ticker": ticker,
        "filing_type": "10-K",
        "period": "2019-02-07",
        "page_number": None,
        "table_rows": [["bulk"] * 40],  # must not be stored
    }


CHUNKS = [
    _chunk("capex", "Purchases of property, plant and equipment (PP&E) $ (1,577)"),
    _chunk("nvda", "Nvidia data center revenue grew significantly", "NVDA"),
    _chunk("aapl", "Apple iPhone revenue declined slightly this quarter", "AAPL"),
    _chunk("tsla", "Tesla vehicle deliveries increased in the quarter", "TSLA"),
]


@pytest.fixture
def index(tmp_path):
    path = tmp_path / "kw.sqlite"
    build_keyword_index(path, iter(CHUNKS))
    return KeywordIndex(path)


def test_ranks_the_most_relevant_chunk_first(index):
    hits = index.search("Nvidia data center revenue", top_k=1)
    assert [h["chunk_id"] for h in hits] == ["nvda"]


def test_punctuation_does_not_block_a_match(index):
    """rank-bm25 tokenised with .split(), so "property," never matched
    "property" -- the capex line was unreachable by keyword search."""
    hits = index.search("property plant equipment", top_k=1)
    assert hits and hits[0]["chunk_id"] == "capex"


def test_stemming_matches_inflected_forms(index):
    assert index.search("purchase", top_k=1)[0]["chunk_id"] == "capex"


def test_returns_only_the_fields_retrieval_reads(index):
    hit = index.search("Tesla deliveries", top_k=1)[0]
    assert set(hit) == set(BM25_CHUNK_FIELDS)
    assert hit["text"].startswith("Tesla")
    assert hit["ticker"] == "TSLA"


def test_fts_query_syntax_in_user_input_cannot_break_or_steer_search(index):
    """Raw query text must never reach MATCH as FTS5 syntax -- quotes, NEAR,
    column filters and bare operators either raise a syntax error or change
    what is searched."""
    for hostile in ['revenue" OR "x', 'NEAR(revenue apple)', "text: revenue", "revenue AND",
                    "-revenue", "(((", '"', "*"]:
        index.search(hostile, top_k=3)  # must not raise


def test_no_match_and_empty_query_return_empty(index):
    assert index.search("zzzqqq", top_k=5) == []
    assert index.search("", top_k=5) == []
    assert index.search("   ...   ", top_k=5) == []


def test_respects_top_k(index):
    assert len(index.search("revenue quarter", top_k=1)) == 1


def test_load_downloads_once_then_reuses_the_local_copy(tmp_path):
    """A warm Lambda must not re-download a ~1 GB file on every request."""
    built = tmp_path / "built.sqlite"
    build_keyword_index(built, iter(CHUNKS))
    s3 = MagicMock()
    s3.download_file.side_effect = lambda b, k, dest: open(dest, "wb").write(built.read_bytes())

    local = tmp_path / "cache" / "kw.sqlite"
    first = load_keyword_index(s3, "bucket", "key", local)
    second = load_keyword_index(s3, "bucket", "key", local)

    assert s3.download_file.call_count == 1
    assert first.search("Tesla", top_k=1)[0]["chunk_id"] == "tsla"
    assert second.search("Tesla", top_k=1)[0]["chunk_id"] == "tsla"


def test_interrupted_download_is_not_mistaken_for_a_complete_index(tmp_path):
    """A half-written file left at the final path would be reused forever by
    the download-once check above. Downloads land on a temp name first."""
    s3 = MagicMock()

    def die_midway(bucket, key, dest):
        open(dest, "wb").write(b"partial")
        raise botocore.exceptions.ReadTimeoutError(endpoint_url="https://s3/x")

    s3.download_file.side_effect = die_midway
    local = tmp_path / "kw.sqlite"

    with pytest.raises(botocore.exceptions.ReadTimeoutError):
        load_keyword_index(s3, "bucket", "key", local, max_retries=2, retry_delay=0)

    assert not local.exists(), "partial download was left at the final path"


def test_read_timeout_is_retried(tmp_path):
    built = tmp_path / "built.sqlite"
    build_keyword_index(built, iter(CHUNKS))
    calls = {"n": 0}

    def flaky(bucket, key, dest):
        calls["n"] += 1
        if calls["n"] < 3:
            raise botocore.exceptions.ReadTimeoutError(endpoint_url="https://s3/x")
        open(dest, "wb").write(built.read_bytes())

    s3 = MagicMock()
    s3.download_file.side_effect = flaky

    idx = load_keyword_index(s3, "b", "k", tmp_path / "kw.sqlite", max_retries=5, retry_delay=0)
    assert calls["n"] == 3
    assert idx.search("Tesla", top_k=1)


def _dated(cid, ticker, period):
    return {**_chunk(cid, "Purchases of property, plant and equipment (PP&E)", ticker),
            "period": period}


def test_search_filters_by_ticker_and_period_window(tmp_path):
    """Same PP&E wording in every filing -- only the filters can tell the
    FY2018 10-K apart from look-alikes in other years or companies."""
    db = tmp_path / "kw.sqlite"
    build_keyword_index(db, [
        _dated("mmm-2019", "MMM", "2019-02-07"),
        _dated("mmm-2023", "MMM", "2023-02-08"),
        _dated("pfe-2019", "PFE", "2019-02-28"),
    ])
    index = KeywordIndex(db)

    hits = index.search("property plant equipment", top_k=10, ticker="MMM",
                        period_range=("2018-01-01", "2019-12-31"))

    assert [h["chunk_id"] for h in hits] == ["mmm-2019"]


def test_search_without_filters_is_unchanged(tmp_path):
    db = tmp_path / "kw.sqlite"
    build_keyword_index(db, [_dated("a", "MMM", "2019-02-07"), _dated("b", "PFE", "2023-01-01")])

    assert len(KeywordIndex(db).search("property plant equipment", top_k=10)) == 2

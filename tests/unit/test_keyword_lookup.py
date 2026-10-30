"""chunk_lookup and coverage tables: id lookups must not scan the corpus.

chunk_id is an UNINDEXED FTS5 column; looking one passage up by id scanned
all 171,790 rows (2.3 s measured) versus 8 ms by rowid.
"""
import sqlite3

from pipeline.sync_pinecone import KeywordIndex, add_lookup_tables, build_keyword_index

LONG_TEXT = "Purchases of property, plant and equipment (PP&E) (1,577)" + " row" * 400
CHUNKS = [
    {"chunk_id": "a1", "text": LONG_TEXT, "ticker": "MMM", "filing_type": "10-K",
     "period": "2019-02-07", "page_number": 40},
    {"chunk_id": "b2", "text": "Net sales 32,765", "ticker": "MMM", "filing_type": "10-K",
     "period": "2019-02-07", "page_number": 38},
    {"chunk_id": "c3", "text": "Revenue 26,044", "ticker": "NVDA", "filing_type": "10-Q",
     "period": "2025-05-28", "page_number": None},
]


def _index(tmp_path):
    path = tmp_path / "kw.sqlite"
    build_keyword_index(path, CHUNKS)
    return KeywordIndex(path)


def test_get_by_ids_returns_full_text_keyed_by_id(tmp_path):
    found = _index(tmp_path).get_by_ids(["a1", "c3"])
    assert set(found) == {"a1", "c3"}
    assert found["a1"]["text"] == LONG_TEXT  # whole chunk, not Pinecone's 1,000-char cut
    assert found["a1"]["page_number"] == 40
    assert found["c3"]["ticker"] == "NVDA"


def test_get_by_ids_skips_unknown_ids_and_empty_input(tmp_path):
    index = _index(tmp_path)
    assert index.get_by_ids(["nope"]) == {}
    assert index.get_by_ids([]) == {}


def test_coverage_lists_each_filing_once_with_its_chunk_count(tmp_path):
    assert _index(tmp_path).coverage() == [
        {"ticker": "MMM", "filing_type": "10-K", "filed": "2019-02-07", "chunks": 2},
        {"ticker": "NVDA", "filing_type": "10-Q", "filed": "2025-05-28", "chunks": 1},
    ]


def test_add_lookup_tables_upgrades_an_index_built_without_them(tmp_path):
    """The published index predates these tables; the upgrade script adds them in place."""
    path = tmp_path / "kw.sqlite"
    build_keyword_index(path, CHUNKS)
    conn = sqlite3.connect(path)
    conn.executescript("DROP TABLE chunk_lookup; DROP TABLE coverage;")
    add_lookup_tables(conn)
    conn.close()
    assert set(KeywordIndex(path).get_by_ids(["a1", "b2"])) == {"a1", "b2"}

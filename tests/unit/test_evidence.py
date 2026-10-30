from unittest.mock import MagicMock

import pytest

from server.retrieval.evidence import (
    KEYWORD_ONLY_NOTE,
    MAX_PASSAGE_CHARS,
    NO_MATCH_NOTE,
    find_passages,
    format_citation,
    to_passage,
)
from tests.unit.mcp_helpers import FakeKeywordIndex, chunk, pinecone_returning

CAPEX_ROW = "Purchases of property, plant and equipment (PP&E) (1,577)"
FULL_TEXT = "Cash flows from investing activities " * 40 + CAPEX_ROW  # row past char 1,000


def _embed(text):
    return [0.1, 0.2]


def test_dense_hit_comes_back_with_full_text_not_pinecones_1000_char_cut():
    full = chunk("d1", FULL_TEXT)
    index = FakeKeywordIndex([full], bm25_ids=[])
    pinecone = pinecone_returning([{"id": "d1", "metadata": {**full, "text": FULL_TEXT[:1000]}}])

    chunks, note = find_passages("3M capital expenditure 2018", pinecone, index, _embed)

    assert note is None
    assert [c["chunk_id"] for c in chunks] == ["d1"]
    assert CAPEX_ROW in chunks[0]["text"]


def test_gaap_wording_reaches_the_keyword_search():
    index = FakeKeywordIndex([chunk("a1", CAPEX_ROW)])
    find_passages("3M capital expenditure 2018", pinecone_returning([]), index, _embed)
    assert "purchases of property plant and equipment" in index.queries[0]["query"]


def test_explicit_years_set_the_filing_date_window():
    index = FakeKeywordIndex([chunk("a1", CAPEX_ROW)])
    find_passages("capex", pinecone_returning([]), index, _embed, ticker="MMM", years=(2018, 2018))
    assert index.queries[0]["period_range"] == ("2018-01-01", "2019-12-31")
    assert index.queries[0]["ticker"] == "MMM"


def test_explicit_ticker_is_strict_even_when_only_other_companies_match():
    index = FakeKeywordIndex([chunk("n1", "Revenue 26,044", ticker="NVDA")])
    chunks, note = find_passages("revenue", pinecone_returning([]), index, _embed, ticker="MMM")
    assert chunks == []
    assert note == NO_MATCH_NOTE


def test_embedding_failure_falls_back_to_keyword_search_with_a_note():
    index = FakeKeywordIndex([chunk("a1", CAPEX_ROW)])
    broken_embed = MagicMock(side_effect=RuntimeError("429 insufficient_quota"))

    chunks, note = find_passages(
        "3M capital expenditure", pinecone_returning([]), index, broken_embed
    )

    assert [c["chunk_id"] for c in chunks] == ["a1"]
    assert note == KEYWORD_ONLY_NOTE


def test_candidates_stage_skips_rerank_and_returns_everything():
    index = FakeKeywordIndex([chunk(f"c{i}", f"capital expenditure {i}") for i in range(8)])
    chunks, _ = find_passages("capital expenditure", pinecone_returning([]), index, _embed,
                              stage="candidates")
    assert len(chunks) == 8


def test_unknown_stage_is_rejected():
    with pytest.raises(ValueError):
        find_passages("q", pinecone_returning([]), FakeKeywordIndex([]), _embed, stage="nope")


def test_to_passage_formats_citation_and_caps_text():
    passage = to_passage(chunk("a1", "x" * (MAX_PASSAGE_CHARS + 50)))
    assert passage["id"] == "a1"
    assert passage["citation"] == "[MMM 10-K 2019-02-07 p.40]"
    assert passage["form"] == "10-K" and passage["filed"] == "2019-02-07" and passage["page"] == 40
    assert passage["text"].endswith("[... truncated]")
    assert len(passage["text"]) < MAX_PASSAGE_CHARS + 30


def test_citation_omits_page_when_unknown():
    assert format_citation(chunk("a1", "t", page=None)) == "[MMM 10-K 2019-02-07]"

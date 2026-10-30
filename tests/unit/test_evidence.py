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


def test_lowercase_ticker_is_normalised():
    index = FakeKeywordIndex([chunk("a1", CAPEX_ROW)])
    chunks, _ = find_passages("capex", pinecone_returning([]), index, _embed, ticker="mmm")
    assert [c["chunk_id"] for c in chunks] == ["a1"]


@pytest.mark.parametrize("q", ["", "   "])
def test_empty_question_is_rejected(q):
    with pytest.raises(ValueError):
        find_passages(q, pinecone_returning([]), FakeKeywordIndex([]), _embed)


def test_years_with_no_matching_filing_are_flagged():
    index = FakeKeywordIndex([chunk("a1", CAPEX_ROW, period="2023-02-08")])
    chunks, note = find_passages("capex", pinecone_returning([]), index, _embed,
                                 ticker="MMM", years=(2018, 2018))
    assert [c["chunk_id"] for c in chunks] == ["a1"]
    assert "2018" in note and "other years" in note


def test_keyword_note_is_kept_when_nothing_matches():
    index = FakeKeywordIndex([])
    broken = MagicMock(side_effect=RuntimeError("down"))
    chunks, note = find_passages("revenue", pinecone_returning([]), index, broken)
    assert chunks == []
    assert note == f"{KEYWORD_ONLY_NOTE} {NO_MATCH_NOTE}"


NFLX_Q = chunk("q1", "Netflix revenue for the quarter 8,541,668", ticker="NFLX",
               filing_type="10-Q", period="2023-10-20")
NFLX_K = chunk("k1", "Netflix revenues 33,723,297 for the year", ticker="NFLX",
               filing_type="10-K", period="2024-01-26")


def test_fiscal_year_question_prefers_the_annual_report_over_10qs():
    """'Netflix revenue FY2023' ranked 10-Qs over the FY2023 10-K (2026-10-30)."""
    index = FakeKeywordIndex([NFLX_Q, NFLX_K])
    chunks, _ = find_passages("Netflix revenue FY2023", pinecone_returning([]), index, _embed)
    assert [c["chunk_id"] for c in chunks] == ["k1"]


def test_quarter_question_keeps_10qs():
    index = FakeKeywordIndex([NFLX_Q, NFLX_K])
    chunks, _ = find_passages(
        "Netflix revenue for the third quarter of 2023", pinecone_returning([]), index, _embed
    )
    assert "q1" in [c["chunk_id"] for c in chunks]


def test_annual_question_keeps_10qs_when_no_10k_was_found():
    index = FakeKeywordIndex([NFLX_Q])
    chunks, _ = find_passages("Netflix revenue FY2023", pinecone_returning([]), index, _embed)
    assert [c["chunk_id"] for c in chunks] == ["q1"]


def test_fiscal_year_argument_also_prefers_the_annual_report():
    index = FakeKeywordIndex([NFLX_Q, NFLX_K])
    chunks, _ = find_passages(
        "Netflix revenue", pinecone_returning([]), index, _embed, ticker="NFLX", years=(2023, 2023)
    )
    assert [c["chunk_id"] for c in chunks] == ["k1"]


# pd.read_html serialization, as stored for 45% of chunks (Amcor FY2020 10-K).
RAW_TABLE = "\n".join([
    "0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8",
    " |  |  |  |  |  |  |  | ",
    "(In millions) | (In millions) |  | 2020 | 2020 |  | 2019 | 2019 | ",
    "Net sales | Net sales |  | $ | 12467.5 |  | $ | 9458.2 | ",
    "Dividends per share | Dividends per share |  | 0.20 |  |  | 0.20 |  | ",
    "Other | Other |  | (17 | ) |  | 3.5 | % | ",
])


def test_table_text_drops_column_numbers_spacers_and_colspan_copies():
    from server.retrieval.evidence import clean_table_text

    assert clean_table_text(RAW_TABLE) == "\n".join([
        "(In millions) | 2020 | 2019",
        "Net sales | $12467.5 | $9458.2",
        "Dividends per share | 0.20 | 0.20",
        "Other | (17) | 3.5%",
    ])


def test_equal_values_in_neighbouring_columns_are_kept():
    """Collapsing 0.20 | 0.20 across two years would shift every column after it."""
    from server.retrieval.evidence import clean_table_text

    table = "0 | 1 | 2\n | 2020 | 2019\nEPS | 0.20 | 0.20"
    assert clean_table_text(table) == " | 2020 | 2019\nEPS | 0.20 | 0.20"


def test_an_empty_cell_keeps_its_column():
    """Dropping a blank 2020 cell would put the 2019 value under 2020."""
    from server.retrieval.evidence import clean_table_text

    table = "0 | 1 | 2\n | 2020 | 2019\nGoodwill impairment |  | 41"
    assert clean_table_text(table).splitlines()[1] == "Goodwill impairment |  | 41"


def test_prose_and_real_numeric_headers_are_untouched():
    from server.retrieval.evidence import clean_table_text

    prose = "Revenue grew 4% | driven by cloud."
    assert clean_table_text(prose) == prose
    assert clean_table_text("2020 | 2019\nRevenue | 5 | 4").startswith("2020 | 2019")


def test_passages_reach_the_reranker_and_client_cleaned():
    index = FakeKeywordIndex([chunk("t1", RAW_TABLE)])
    chunks, _ = find_passages("Amcor net sales 2020", pinecone_returning([]), index, _embed)
    assert chunks[0]["text"].startswith("(In millions) | 2020 | 2019")


def test_float_copies_of_a_year_header_merge():
    from server.retrieval.evidence import clean_table_text

    table = (
        "0 | 1 | 2 | 3 | 4\n"
        "As of June 30, | 2026 | 2026.0 | 2025 | 2025.0\n"
        "Cash | $ | 1115 | $ | 827"
    )
    assert clean_table_text(table) == "As of June 30, | 2026 | 2025\nCash | $1115 | $827"

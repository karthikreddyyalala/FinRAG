"""TDD: questions name metrics colloquially; filings label them in GAAP terms.

FinanceBench asks for "capital expenditure", but a cash flow statement calls
that line "Purchases of property, plant and equipment (PP&E)". There is no
lexical overlap on the key term, and a pipe-delimited number table embeds
poorly, so both retrieval arms miss the one chunk that holds the answer.
Bridging that vocabulary gap is what makes the figure reachable at all.
"""
from server.retrieval.query_rewriter import GAAP_SYNONYMS, expand_financial_terms


def test_capex_expands_to_the_cash_flow_line_item():
    out = expand_financial_terms("What is the FY2018 capital expenditure amount for 3M?")
    assert "property" in out.lower()
    assert "equipment" in out.lower()


def test_original_query_is_preserved():
    """Expansion appends context; it must not replace what the user asked."""
    q = "What is the FY2018 capital expenditure amount for 3M?"
    out = expand_financial_terms(q)
    assert q in out, "original query text was lost"


def test_query_without_known_metric_is_unchanged():
    q = "Who are the primary customers of Boeing?"
    assert expand_financial_terms(q) == q


def test_matching_is_case_insensitive():
    assert "property" in expand_financial_terms("3M CAPITAL EXPENDITURE 2018").lower()


def test_no_duplicate_expansion_when_gaap_term_already_present():
    """If the question already uses the filing's wording, adding it again
    just dilutes the query."""
    q = "3M purchases of property plant and equipment 2018"
    assert expand_financial_terms(q) == q


def test_every_synonym_value_is_nonempty():
    for term, expansion in GAAP_SYNONYMS.items():
        assert expansion.strip(), f"empty expansion for {term!r}"
        assert term.lower() == term, f"key {term!r} must be lowercase for matching"

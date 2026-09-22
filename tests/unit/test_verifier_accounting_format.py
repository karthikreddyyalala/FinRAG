"""TDD: grounding must survive how financial tables actually format numbers.

Filings wrap negatives in parentheses and separate the currency symbol from
the value across table cells: "$ | (1,577)". An answer correctly reporting
that as "$1,577 million" shares no literal substring with the source, so
string matching strikes out a figure that is genuinely grounded -- exactly
what happened to FinanceBench Q1 after retrieval was fixed.
"""
from server.retrieval.numerical_verifier import verify_answer

# Verbatim shape of a cash flow statement chunk, pipes and all.
TABLE_SOURCE = (
    "Years ended December 31 | (Millions) | 2018 | 2017 | 2016\n"
    "Purchases of property, plant and equipment (PP&E) |  | $ | (1,577) |  | $ | (1,373)"
)


def test_magnitude_of_a_parenthesised_source_figure_is_grounded():
    """(1,577) in the source grounds "$1,577" in the answer -- the parentheses
    are the accounting sign convention, not part of the value."""
    answer = "3M spent $1,577 million on capital expenditures in FY2018."
    result = verify_answer(answer, [TABLE_SOURCE])
    assert "1,577" in result, f"grounded figure was struck out: {result!r}"
    assert "unavailable" not in result, f"figure wrongly flagged: {result!r}"


def test_currency_split_across_table_cells_still_grounds():
    """"$ | (1,373)" grounds an answer saying "$1,373"."""
    answer = "The prior year figure was $1,373 million."
    result = verify_answer(answer, [TABLE_SOURCE])
    assert "unavailable" not in result, f"figure wrongly flagged: {result!r}"


def test_hallucinated_figure_is_still_caught():
    """The grounding guarantee must not be weakened by the above."""
    answer = "3M spent $9,999 million on capital expenditures."
    result = verify_answer(answer, [TABLE_SOURCE])
    assert "unavailable" in result, f"hallucinated figure passed: {result!r}"


def test_prefix_of_a_source_number_is_still_not_grounded():
    """Numeric comparison must not reintroduce the substring bug: $1,57 is
    not $1,577."""
    answer = "The amount was $157 million."
    result = verify_answer(answer, [TABLE_SOURCE])
    assert "unavailable" in result, f"prefix wrongly treated as grounded: {result!r}"

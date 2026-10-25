"""Bucket logic for evals/failure_breakdown.py (no model calls)."""

from evals.failure_breakdown import classify

CACHE = {"MMM": {"10-K": {2019}}}
Q = {"ticker": "3M", "filing_type": "10k", "period": 2018}


def row(answer: str, contexts: list[str]) -> dict:
    return {"answer": answer, "contexts": contexts, "ground_truth": "$1577.00"}


def test_earnings_questions_are_out_of_scope():
    assert classify(row("x", []), {**Q, "filing_type": "Earnings"}, CACHE) == "out_of_scope"


def test_missing_filing_year_is_a_data_gap():
    assert classify(row("x", []), {**Q, "period": 2010}, CACHE) == "no_filing_in_corpus"


def test_correct_refused_and_wrong_are_told_apart():
    assert classify(row("Capex was $(1,577).", []), Q, CACHE) == "correct"
    refused = row("The context does not provide this figure.", ["capex was 1,577"])
    assert classify(refused, Q, CACHE) == "refused_data_in_ctx"
    missed = row("The context does not provide it.", ["nothing"])
    assert classify(missed, Q, CACHE) == "refused_retrieval"
    assert classify(row("It was $999 million.", ["nothing"]), Q, CACHE) == "wrong_retrieval"

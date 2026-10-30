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


def test_missing_docs_lists_uncovered_filings():
    from evals.failure_breakdown import missing_docs

    rows = [
        {"doc_name": "MICROSOFT_2016_10K", "company": "Microsoft"},
        {"doc_name": "MICROSOFT_2016_10K", "company": "Microsoft"},
        {"doc_name": "MICROSOFT_2023_10K", "company": "Microsoft"},
        {"doc_name": "JPMORGAN_2021Q1_10Q", "company": "JPMorgan"},
        {"doc_name": "NETFLIX_2022Q4_EARNINGS", "company": "Netflix"},
    ]
    cache = {"MSFT": {"10-K": {2023, 2024}}, "JPM": {"10-Q": {2021}}}
    assert missing_docs(rows, cache) == ["MICROSOFT_2016_10K"]


def test_main_scores_a_given_answers_file(tmp_path, capsys):
    import json

    from evals import failure_breakdown as fb

    questions = json.loads(fb.QUESTIONS.read_text())
    rows = [
        {"question": q["question"], "answer": "The context does not provide it.",
         "contexts": [], "ground_truth": q["ground_truth"]}
        for q in questions
    ]
    path = tmp_path / "answers.json"
    path.write_text(json.dumps(rows))
    fb.main(["--answers", str(path)])
    out = capsys.readouterr().out
    assert "out_of_scope" in out and "total" in out


def test_a_refusal_that_happens_to_contain_the_number_is_not_correct():
    answer = "The context does not provide 3M's capex, so I cannot confirm $1,577 million."
    assert classify(row(answer, []), Q, CACHE) == "refused_retrieval"

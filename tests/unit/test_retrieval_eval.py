from evals.retrieval_eval import score_retrieval


def fake_search(question):
    # right chunk is 3rd for question A, absent for question B
    if question == "A":
        return [{"text": "nothing"}, {"text": "nope"}, {"text": "capex was 1,577"}]
    return [{"text": "nothing"}]


def test_hit_at_k_and_mrr():
    items = [
        {"question": "A", "ground_truth": "$1577.00"},
        {"question": "B", "ground_truth": "$1577.00"},
    ]
    r = score_retrieval(items, fake_search)
    assert r["n"] == 2
    assert r["hit@1"] == 0.0
    assert r["hit@5"] == 0.5
    assert r["hit@20"] == 0.5
    assert round(r["mrr"], 3) == round((1 / 3 + 0) / 2, 3)


EVIDENCE = (
    "CONSOLIDATED STATEMENTS OF INCOME Year Ended December 31, 2021 2020 "
    "Net Operating Revenues $ 38,655 $ 33,014 Cost of goods sold 15,357 13,433 Gross Profit 23,298"
)


def test_evidence_hit_needs_the_statement_numbers_not_just_the_topic():
    from evals.retrieval_eval import covers_evidence

    statement_chunk = "Net operating revenues 38,655 33,014 Cost of goods sold 15,357 13,433"
    prose_chunk = "Cost of goods sold increased because of commodity prices in 2021."
    assert covers_evidence(statement_chunk, [EVIDENCE])
    assert not covers_evidence(prose_chunk, [EVIDENCE])


def test_score_evidence_reports_hit_at_k():
    from evals.retrieval_eval import score_evidence

    items = [{"question": "q", "evidence": [EVIDENCE]}]
    hit = {"text": "Net operating revenues 38,655 Cost of goods sold 15,357 13,433"}
    chunks = [{"text": "nothing"}, hit]
    r = score_evidence(items, lambda q: chunks)
    assert r["hit@1"] == 0.0 and r["hit@5"] == 1.0 and r["n"] == 1


def test_evidence_items_keep_in_scope_questions_that_have_evidence(monkeypatch):
    from evals import failure_breakdown as fb
    from evals.retrieval_eval import evidence_items

    monkeypatch.setattr(fb, "has_filing", lambda q, cache: q["ticker"] == "3M")
    questions = [
        {"question": "a", "ticker": "3M", "filing_type": "10k"},
        {"question": "b", "ticker": "AMD", "filing_type": "10k"},
        {"question": "c", "ticker": "3M", "filing_type": "Earnings"},
        {"question": "d", "ticker": "3M", "filing_type": "10k"},
    ]
    docs = [
        {"question": "a", "evidence": ["e1"]},
        {"question": "b", "evidence": ["e2"]},
        {"question": "c", "evidence": ["e3"]},
        {"question": "d", "evidence": []},
    ]
    assert evidence_items(questions, docs) == [{"question": "a", "evidence": ["e1"]}]


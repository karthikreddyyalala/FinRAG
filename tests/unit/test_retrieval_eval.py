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

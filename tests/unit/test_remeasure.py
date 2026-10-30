# ruff: noqa: E501
from evals.run_remeasure import summarize


def test_summarize_counts():
    rows = [
        {"answer": "Revenue was $1,577 million.", "contexts": ["net sales 1,577"], "ground_truth": "$1,577 million"},
        {"answer": "The context does not provide it.", "contexts": ["x"], "ground_truth": "$900 million"},
        {"answer": "It was $5,000.", "contexts": ["y"], "ground_truth": "no number"},
    ]
    s = summarize(rows, check=True)
    assert s["n"] == 3 and s["refused"] == 1
    assert s["states_true_number"]["hits"] == 1 and s["states_true_number"]["denominator"] == 2
    assert s["verify_figures"]["total_not_found"] == 1

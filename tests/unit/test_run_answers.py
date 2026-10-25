from pathlib import Path

from evals.run_answers import answers_path


def test_answers_path_never_overwrites_the_baseline_file():
    p = answers_path("after_coverage")
    assert p.name == "financebench_answers_after_coverage.json"
    assert p != Path(p.parent / "financebench_answers.json")


def test_filter_items_keeps_only_the_requested_companies():
    from evals.run_answers import filter_items

    items = [{"ticker": "3M"}, {"ticker": "Coca-Cola"}, {"ticker": "Walmart"}]
    assert filter_items(items, {"MMM", "KO"}) == [{"ticker": "3M"}, {"ticker": "Coca-Cola"}]


def test_ratio_items_keeps_only_derived_metric_questions():
    from evals.run_answers import ratio_items

    items = [
        {"question": "What is Kraft Heinz's FY2019 inventory turnover ratio?"},
        {"question": "What was 3M's capital expenditure in FY2018?"},
        {"question": "FY2021 COGS % margin for Coca Cola?"},
    ]
    assert [i["question"][:12] for i in ratio_items(items)] == ["What is Kraf", "FY2021 COGS "]

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

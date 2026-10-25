from pathlib import Path

from evals.run_answers import answers_path


def test_answers_path_never_overwrites_the_baseline_file():
    p = answers_path("after_coverage")
    assert p.name == "financebench_answers_after_coverage.json"
    assert p != Path(p.parent / "financebench_answers.json")

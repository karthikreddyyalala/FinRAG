"""Answer the FinanceBench questions and save them, with no ragas scoring.

Cheaper and faster than run_eval.py when the question is "what changed in the
answers": it runs the pipeline once per question and checkpoints after each, so
a crash resumes. The output goes to its own file so the baseline answers are
never overwritten; feed it to evals/failure_breakdown.py --answers.

Run: PYTHONPATH=. python3 evals/run_answers.py LABEL
"""
from __future__ import annotations

import sys
from pathlib import Path

from evals.run_eval import FINANCEBENCH, RESULTS_DIR, _init_clients, _load, _run_dataset


def answers_path(label: str) -> Path:
    return RESULTS_DIR / f"financebench_answers_{label}.json"


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: run_answers.py LABEL")
        sys.exit(1)
    path = answers_path(sys.argv[1])
    clients = _init_clients()
    items = _load(FINANCEBENCH)
    print(f"Answering {len(items)} questions -> {path}", flush=True)
    _run_dataset(items, "FB", clients, path)


if __name__ == "__main__":
    main()

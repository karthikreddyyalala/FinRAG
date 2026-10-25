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

from evals.failure_breakdown import NAME_TO_TICKER
from evals.run_eval import FINANCEBENCH, RESULTS_DIR, _init_clients, _load, _run_dataset


def answers_path(label: str) -> Path:
    return RESULTS_DIR / f"financebench_answers_{label}.json"


def filter_items(items: list[dict], tickers: set[str]) -> list[dict]:
    """Keep only the questions about these tickers (dataset uses company names)."""
    return [i for i in items if NAME_TO_TICKER.get(i["ticker"], i["ticker"]) in tickers]


def main() -> None:
    args = sys.argv[1:]
    tickers: set[str] = set()
    if "--tickers" in args:
        i = args.index("--tickers")
        tickers = set(args[i + 1].split(","))
        del args[i : i + 2]
    if len(args) != 1:
        print("Usage: run_answers.py LABEL [--tickers MMM,AMD,KO]")
        sys.exit(1)
    path = answers_path(args[0])
    clients = _init_clients()
    items = _load(FINANCEBENCH)
    if tickers:
        items = filter_items(items, tickers)
    print(f"Answering {len(items)} questions -> {path}", flush=True)
    _run_dataset(items, "FB", clients, path)


if __name__ == "__main__":
    main()

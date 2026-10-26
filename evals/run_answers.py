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
from server.retrieval.ratio_plan import line_items_for


def answers_path(label: str) -> Path:
    return RESULTS_DIR / f"financebench_answers_{label}.json"


def filter_items(items: list[dict], tickers: set[str]) -> list[dict]:
    """Keep only the questions about these tickers (dataset uses company names)."""
    return [i for i in items if NAME_TO_TICKER.get(i["ticker"], i["ticker"]) in tickers]


def scorable_only(items: list[dict]) -> list[dict]:
    """Questions with an ingested filing and a numeric ground truth (the 92)."""
    from evals.analyze_baseline_gap import _significant_numbers
    from evals.failure_breakdown import FORM, has_filing

    cache: dict = {}
    return [
        i for i in items
        if i["filing_type"] in FORM and has_filing(i, cache)
        and _significant_numbers(i["ground_truth"], 1.5)
    ]


def ratio_items(items: list[dict]) -> list[dict]:
    """Questions about a derived metric (the ones the ratio planner targets)."""
    return [i for i in items if line_items_for(i["question"])]


def main() -> None:
    args = sys.argv[1:]
    tickers: set[str] = set()
    if "--tickers" in args:
        i = args.index("--tickers")
        tickers = set(args[i + 1].split(","))
        del args[i : i + 2]
    only_scorable = "--scorable" in args
    if only_scorable:
        args.remove("--scorable")
    if "--no-rerank" in args:
        # A/B: take the first top_k candidates instead of reranking them.
        args.remove("--no-rerank")
        import server.mcp_tools.search_filings as search_filings

        search_filings.rerank = lambda q, c, top_k=5, lexical_query=None: c[:top_k]
    only_ratio = "--ratio-only" in args
    if only_ratio:
        args.remove("--ratio-only")
    if len(args) != 1:
        print(
            "Usage: run_answers.py LABEL [--tickers MMM,AMD] [--ratio-only] "
            "[--scorable] [--no-rerank]"
        )
        sys.exit(1)
    path = answers_path(args[0])
    clients = _init_clients()
    items = _load(FINANCEBENCH)
    if tickers:
        items = filter_items(items, tickers)
    if only_ratio:
        items = ratio_items(items)
    if only_scorable:
        items = scorable_only(items)
    print(f"Answering {len(items)} questions -> {path}", flush=True)
    _run_dataset(items, "FB", clients, path)


if __name__ == "__main__":
    main()

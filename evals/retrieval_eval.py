"""Does the right number reach the top-k chunks? Deterministic, no LLM judge.

A chunk is a hit when it contains the ground truth's number (same 2% rule the
failure breakdown uses). Measures retrieval on its own, apart from generation.

Run: PYTHONPATH=. python3 evals/retrieval_eval.py [--stage candidates|reranked]
Needs live Pinecone and the keyword index (see evals/run_eval.py _init_clients).
"""
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

from evals.failure_breakdown import truth_in_contexts

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"


def score_retrieval(items: list[dict], search: Callable[[str], list[dict]]) -> dict:
    """hit@1/5/10 and MRR over items whose ground truth has a number."""
    n = h1 = h5 = h10 = 0
    reciprocal = 0.0
    for item in items:
        chunks = search(item["question"])
        rank = next(
            (
                i + 1
                for i, c in enumerate(chunks)
                if truth_in_contexts(item["ground_truth"], [c.get("text", "")])
            ),
            None,
        )
        n += 1
        if rank:
            reciprocal += 1 / rank
            h1 += rank <= 1
            h5 += rank <= 5
            h10 += rank <= 10
    total = max(n, 1)
    return {
        "n": n,
        "hit@1": h1 / total,
        "hit@5": h5 / total,
        "hit@10": h10 / total,
        "mrr": reciprocal / total,
    }


def scorable_items(questions: list[dict]) -> list[dict]:
    """Questions with an ingested filing and a numeric ground truth."""
    from evals.analyze_baseline_gap import _significant_numbers
    from evals.failure_breakdown import FORM, has_filing

    cache: dict = {}
    return [
        {"question": q["question"], "ground_truth": q["ground_truth"]}
        for q in questions
        if q["filing_type"] in FORM
        and has_filing(q, cache)
        and _significant_numbers(q["ground_truth"], 1.5)
    ]


def main() -> None:
    from evals.run_eval import _init_clients
    from server.mcp_tools.search_filings import retrieve_chunks

    stage = "reranked"
    if "--stage" in sys.argv:
        stage = sys.argv[sys.argv.index("--stage") + 1]
    clients = _init_clients()
    questions = json.loads((ROOT / "eval_data" / "financebench_150.json").read_text())
    items = scorable_items(questions)
    print(f"{len(items)} scorable questions, stage={stage}", flush=True)
    result = score_retrieval(items, lambda q: retrieve_chunks(q, *clients, stage=stage))
    print(json.dumps(result, indent=2))
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"retrieval_{stage}.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

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
    """hit@1/5/10/20 and MRR over items whose ground truth has a number."""
    n = h1 = h5 = h10 = h20 = 0
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
            h20 += rank <= 20
    total = max(n, 1)
    return {
        "n": n,
        "hit@1": h1 / total,
        "hit@5": h5 / total,
        "hit@10": h10 / total,
        "hit@20": h20 / total,
        "mrr": reciprocal / total,
    }


def _evidence_numbers(texts: list[str]) -> set[float]:
    from evals.analyze_baseline_gap import _extract_numbers

    return {
        n for t in texts for n in _extract_numbers(t)
        if abs(n) >= 100 and not (1990 <= n <= 2035 and n == int(n))
    }


def covers_evidence(chunk_text: str, evidence: list[str]) -> bool:
    """True when the chunk holds the statement's numbers, not merely its topic.

    CAUTION: this measures "did retrieval return the benchmark's exact evidence
    page", not "can the question be answered". Checked against saved answers,
    only 8 of 33 correct answers had their evidence page in the retrieved
    chunks, because the same figures appear in other tables and filings. Use
    it as a diagnostic, never as the success measure; end-to-end correctness is.

    Needs 3 of the evidence's figures (all of them if it has fewer), which a
    prose paragraph about "cost of goods sold" will not contain.
    """
    wanted = _evidence_numbers(evidence)
    if not wanted:
        return False
    have = _evidence_numbers([chunk_text])
    need = min(3, len(wanted))
    matched = sum(
        1 for w in wanted if any(abs(w - h) / max(abs(w), 1e-9) <= 0.001 for h in have)
    )
    return matched >= need


def score_evidence(items: list[dict], search: Callable[[str], list[dict]]) -> dict:
    """hit@k for "a retrieved chunk covers the benchmark's evidence statement"."""
    n = h1 = h5 = h10 = h20 = 0
    for item in items:
        chunks = search(item["question"])
        rank = next(
            (
                i + 1
                for i, c in enumerate(chunks)
                if covers_evidence(c.get("text", ""), item["evidence"])
            ),
            None,
        )
        n += 1
        if rank:
            h1 += rank <= 1
            h5 += rank <= 5
            h10 += rank <= 10
            h20 += rank <= 20
    total = max(n, 1)
    return {"n": n, "hit@1": h1 / total, "hit@5": h5 / total, "hit@10": h10 / total,
            "hit@20": h20 / total}


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


def evidence_items(questions: list[dict], docs: list[dict]) -> list[dict]:
    """In-scope questions (a filing is ingested) paired with their evidence text."""
    from evals.failure_breakdown import FORM, has_filing

    by_question = {d["question"]: d for d in docs}
    cache: dict = {}
    return [
        {"question": q["question"], "evidence": by_question[q["question"]]["evidence"]}
        for q in questions
        if q["filing_type"] in FORM and has_filing(q, cache)
        and by_question.get(q["question"], {}).get("evidence")
    ]


def main() -> None:
    from evals.run_eval import _init_clients
    from server.mcp_tools.search_filings import retrieve_chunks

    stage = "reranked"
    if "--stage" in sys.argv:
        stage = sys.argv[sys.argv.index("--stage") + 1]
    clients = _init_clients()
    questions = json.loads((ROOT / "eval_data" / "financebench_150.json").read_text())
    metric = "number"
    if "--metric" in sys.argv:
        metric = sys.argv[sys.argv.index("--metric") + 1]
    label = sys.argv[sys.argv.index("--label") + 1] if "--label" in sys.argv else ""
    search = lambda q: retrieve_chunks(q, *clients, stage=stage)  # noqa: E731
    if metric == "evidence":
        docs = json.loads((ROOT / "eval_data" / "financebench_docs.json").read_text())
        items = evidence_items(questions, docs)
        print(f"{len(items)} in-scope questions with evidence, stage={stage}", flush=True)
        result = score_evidence(items, search)
    else:
        items = scorable_items(questions)
        print(f"{len(items)} scorable questions, stage={stage}", flush=True)
        result = score_retrieval(items, search)
    print(json.dumps(result, indent=2))
    RESULTS.mkdir(exist_ok=True)
    name = f"retrieval_{metric}_{stage}{('_' + label) if label else ''}.json"
    (RESULTS / name).write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

# ruff: noqa: E501
"""Re-measure answer quality on the current retrieval path; re-score the old answers the same way.

Run: PYTHONPATH=. python evals/run_remeasure.py [--limit N] [--tag m3]
--tag names the checkpoints and result file; any tag but m1 compares against the m1 answers.
Needs OPENAI_API_KEY and PINECONE_API_KEY. Resumable (per-question checkpoints).
"""
from __future__ import annotations

import json
import os
import sys
import time

from evals.analyze_baseline_gap import is_refusal, states_correct_number
from evals.metrics.numerical_accuracy import numerical_accuracy
from evals.run_eval import (
    CUSTOM,
    FINANCEBENCH,
    KEYWORD_INDEX_LOCAL_PATH,
    RESULTS_DIR,
    _load,
    verified_custom_items,
)

PRICE_IN, PRICE_OUT, PRICE_EMB = 0.15 / 1e6, 0.60 / 1e6, 0.02 / 1e6
USAGE = {"in": 0, "out": 0}


class _CountingClient:
    """OpenAI client proxy that tallies token usage for the cost estimate."""

    def __init__(self, client):
        self.chat = self
        self.completions = self
        self._c = client

    def create(self, **kw):
        r = self._c.chat.completions.create(**kw)
        USAGE["in"] += r.usage.prompt_tokens
        USAGE["out"] += r.usage.completion_tokens
        return r


def cost_usd() -> float:
    # embeddings: one short question per item, ~40 tokens; negligible but counted
    return USAGE["in"] * PRICE_IN + USAGE["out"] * PRICE_OUT


def summarize(rows: list[dict], check: bool) -> dict:
    """Metrics for one answer set. `check` adds the verify_figures-style stats (new answers only)."""
    out = {
        "n": len(rows),
        "refused": sum(is_refusal(r["answer"]) for r in rows),
        "numerical_accuracy": numerical_accuracy([r["answer"] for r in rows],
                                                 [r["contexts"] for r in rows]),
    }
    pairs = [(r, states_correct_number(r["answer"], r["ground_truth"])) for r in rows]
    verdicts = [v for _, v in pairs if v is not None]
    # states_correct_number is crude: it also fires on numbers inside refusals (years etc.)
    out["states_true_number_in_non_refusals"] = sum(
        bool(v) for r, v in pairs if v is not None and not is_refusal(r["answer"]))
    out["states_true_number"] = {"hits": sum(verdicts), "denominator": len(verdicts),
                                 "rate": sum(verdicts) / len(verdicts) if verdicts else 0.0}
    if check:
        from server.retrieval.numerical_verifier import check_figures
        nf = [len(check_figures(r["answer"], r["contexts"])[1]) for r in rows]
        out["verify_figures"] = {"answers_with_zero_not_found": sum(n == 0 for n in nf),
                                 "share_zero_not_found": sum(n == 0 for n in nf) / len(rows),
                                 "total_not_found": sum(nf)}
    return out


def answer_all(items, checkpoint, clients, label, limit=None):
    from evals.client_answer import eval_model, write_answer
    from server.retrieval.evidence import find_passages, to_passage

    pinecone_index, keyword_index, embed_fn, oai = clients
    done = {r["question"]: r for r in json.loads(checkpoint.read_text())} if checkpoint.exists() else {}
    rows = []
    for i, item in enumerate(items[:limit], 1):
        q = item["question"]
        if q not in done:
            print(f"  [{label} {i}/{len(items)}] {q[:70]}", flush=True)
            chunks, _ = find_passages(q, pinecone_index, keyword_index, embed_fn)
            passages = [to_passage(c) for c in chunks]
            # raw client answer: no verify_answer rewrite, as the live server never rewrites it
            ans = write_answer(q, passages, client=oai)
            done[q] = {"question": q, "answer": ans, "contexts": [p["text"] for p in passages],
                       "ground_truth": item.get("ground_truth", ""), "model": eval_model()}
            checkpoint.write_text(json.dumps([done[x["question"]] for x in items if x["question"] in done], indent=2))
            time.sleep(1)
        rows.append(done[q])
    return rows


def main() -> None:
    from openai import OpenAI
    from pinecone import Pinecone

    from evals.client_answer import eval_model
    from pipeline.sync_pinecone import get_embed_fn, load_keyword_index

    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "m1"
    # local index only: s3 client None would raise if the file were missing, never touches AWS
    kw = load_keyword_index(None, "", "", KEYWORD_INDEX_LOCAL_PATH)
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index("finrag-filings")
    clients = (pc, kw, get_embed_fn(), _CountingClient(OpenAI(api_key=os.environ["OPENAI_API_KEY"])))

    fb_items = _load(FINANCEBENCH)
    cu_items = verified_custom_items(_load(CUSTOM))
    sfx = "_limit" if limit else ""
    fb_new = answer_all(fb_items, RESULTS_DIR / f"financebench_answers_{tag}{sfx}.json", clients, "FB", limit)
    cu_new = answer_all(cu_items, RESULTS_DIR / f"custom_answers_{tag}{sfx}.json", clients, "Custom", limit)
    if limit:
        print(f"{len(fb_new)}+{len(cu_new)} answered; tokens {USAGE}; cost ${cost_usd():.4f}")
        return

    def old(path, items):
        by_q = {r["question"]: r for r in json.loads((RESULTS_DIR / path).read_text())}
        return [by_q[i["question"]] for i in items]

    base = "" if tag == "m1" else "_m1"
    fb_old = old(f"financebench_answers{base}.json", fb_items)
    cu_old = old(f"custom_answers{base}.json", cu_items)
    result = {
        "date": time.strftime("%Y-%m-%d"),
        "old": f"financebench_answers{base}.json",
        "model": eval_model(),
        "retrieval": "find_passages, same code and index as the live server",
        "financebench": {"new": summarize(fb_new, True), "old": summarize(fb_old, False)},
        "custom": {"new": summarize(cu_new, True), "old": summarize(cu_old, False)},
        "combined": {"new": summarize(fb_new + cu_new, True), "old": summarize(fb_old + cu_old, False)},
        "cost_usd_estimate": round(cost_usd(), 4),
    }
    (RESULTS_DIR / ("remeasure_2026-10-30.json" if tag == "m1" else f"remeasure_{tag}.json")).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

"""Full 300-question eval runner. Outputs evals/results/eval_<timestamp>.json."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

RESULTS_DIR = Path(__file__).parent / "results"
KEYWORD_INDEX_LOCAL_PATH = RESULTS_DIR / "keyword_index.sqlite"
FINANCEBENCH = Path(__file__).parent / "eval_data" / "financebench_150.json"
CUSTOM = Path(__file__).parent / "eval_data" / "custom_150.json"


PLACEHOLDER_GROUND_TRUTH = "VERIFY_AFTER_BOOTSTRAP"


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def verified_custom_items(items: list[dict]) -> list[dict]:
    """Drop custom_150 rows whose ground truth hasn't been verified yet.

    A placeholder ground truth never matches any real answer, so scoring
    against it wouldn't measure the pipeline -- it would just always fail,
    dragging numerical_accuracy down for a reason unrelated to retrieval
    quality (see claude.md Phase D2).
    """
    return [item for item in items if item.get("ground_truth") != PLACEHOLDER_GROUND_TRUTH]


def _init_clients():
    import boto3
    from pinecone import Pinecone

    from pipeline.sync_pinecone import get_embed_fn, load_keyword_index
    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    pinecone_index = pc.Index("finrag-filings")
    s3 = boto3.client("s3", region_name="us-east-1")
    keyword_index = load_keyword_index(
        s3, "finrag-processed-filings", "keyword/index.sqlite", KEYWORD_INDEX_LOCAL_PATH
    )
    embed_fn = get_embed_fn(bedrock)
    return bedrock, pinecone_index, keyword_index, embed_fn


def _call_pipeline(
    question: str, bedrock, pinecone_index, keyword_index, embed_fn, mode: str = "full"
) -> dict:
    from server.mcp_tools.search_filings import build_search_filings_answer
    return build_search_filings_answer(
        query=question,
        bedrock_client=bedrock,
        pinecone_index=pinecone_index,
        keyword_index=keyword_index,
        embed_fn=embed_fn,
        mode=mode,
    )


def _run_dataset(
    items: list[dict], label: str, clients: tuple, checkpoint: Path, mode: str = "full"
) -> tuple[list, list, list, list]:
    """Answer every item, checkpointing after each so a crash resumes cheaply.

    Returns four parallel lists (questions, answers, contexts, ground_truths)
    in `items` order.
    """
    cached: dict[str, dict] = {}
    if checkpoint.exists():
        for row in json.loads(checkpoint.read_text()):
            cached[row["question"]] = row

    # Keyed and returned by `items` order, never by checkpoint order: a
    # checkpoint from a different/older dataset would otherwise score its
    # stale answers against the current questions.
    results: list[dict] = []
    for i, item in enumerate(items, 1):
        question = item["question"]
        if question in cached:
            print(f"  [{label} {i}/{len(items)}] (cached) {question[:70]}", flush=True)
            results.append(cached[question])
            continue

        print(f"  [{label} {i}/{len(items)}] {question[:80]}", flush=True)
        result = _call_pipeline(question, *clients, mode=mode)
        row = {
            "question": question,
            "answer": result.get("answer", ""),
            "contexts": [c.get("text", "") for c in result.get("citations", [])],
            "ground_truth": item.get("ground_truth", ""),
        }
        results.append(row)
        cached[question] = row
        checkpoint.write_text(json.dumps(results, indent=2))
        time.sleep(5)  # pace OpenAI TPM usage

    return (
        [r["question"] for r in results],
        [r["answer"] for r in results],
        [r["contexts"] for r in results],
        [r["ground_truth"] for r in results],
    )


MODES = ("full", "dense_only", "bm25_only")


def main() -> None:
    # --mode dense_only|bm25_only runs CLAUDE.md Phase 4's Baseline A/B
    # instead of the full pipeline, against the same FinanceBench 150 set,
    # so the comparison table is apples-to-apples.
    mode = "full"
    if len(sys.argv) > 1:
        if sys.argv[1] != "--mode" or len(sys.argv) < 3 or sys.argv[2] not in MODES:
            print(f"Usage: run_eval.py [--mode {'|'.join(MODES)}]")
            sys.exit(1)
        mode = sys.argv[2]

    RESULTS_DIR.mkdir(exist_ok=True)
    if not FINANCEBENCH.exists():
        print(f"ERROR: {FINANCEBENCH} not found.")
        sys.exit(1)

    print("Initializing clients (loading BM25 index from S3) ...")
    clients = _init_clients()

    fb_items = _load(FINANCEBENCH)
    print(f"Running {mode} eval: {len(fb_items)} FinanceBench questions")

    suffix = "" if mode == "full" else f"_{mode}"
    checkpoint = RESULTS_DIR / f"financebench_answers{suffix}.json"
    fb_q, fb_a, fb_c, fb_g = _run_dataset(fb_items, "FB", clients, checkpoint, mode=mode)

    # custom_150 is still partially verified (see claude.md Phase D2) --
    # only its confirmed-ground-truth rows are scored, never the
    # VERIFY_AFTER_BOOTSTRAP placeholders.
    custom_items = verified_custom_items(_load(CUSTOM)) if CUSTOM.exists() else []
    custom_q = custom_a = custom_c = custom_g = []
    if custom_items:
        print(f"Running {mode} eval: {len(custom_items)} verified custom questions")
        custom_checkpoint = RESULTS_DIR / f"custom_answers{suffix}.json"
        custom_q, custom_a, custom_c, custom_g = _run_dataset(
            custom_items, "Custom", clients, custom_checkpoint, mode=mode
        )

    from evals.metrics.numerical_accuracy import numerical_accuracy
    from evals.metrics.ragas_metrics import score_dataset

    ts = int(time.time())

    fb_scores = score_dataset(fb_q, fb_a, fb_c, fb_g)
    fb_output = {
        **fb_scores,
        "numerical_accuracy": numerical_accuracy(fb_a, fb_c),
        "n_questions": len(fb_q),
        "dataset": "financebench_150",
        "mode": mode,
    }
    (RESULTS_DIR / f"eval{suffix}_{ts}.json").write_text(json.dumps(fb_output, indent=2))
    RESULTS_DIR.joinpath(f"latest{suffix}.json").write_text(json.dumps(fb_output, indent=2))
    print(f"\nFinanceBench-only results: {fb_output}")

    if custom_items:
        custom_scores = score_dataset(custom_q, custom_a, custom_c, custom_g)
        custom_output = {
            **custom_scores,
            "numerical_accuracy": numerical_accuracy(custom_a, custom_c),
            "n_questions": len(custom_q),
            "dataset": "custom_verified",
            "mode": mode,
        }
        custom_path = RESULTS_DIR / f"eval_custom{suffix}_{ts}.json"
        custom_path.write_text(json.dumps(custom_output, indent=2))
        print(f"Custom-only results: {custom_output}")

        combined_q = fb_q + custom_q
        combined_a = fb_a + custom_a
        combined_c = fb_c + custom_c
        combined_g = fb_g + custom_g
        combined_scores = score_dataset(combined_q, combined_a, combined_c, combined_g)
        combined_output = {
            **combined_scores,
            "numerical_accuracy": numerical_accuracy(combined_a, combined_c),
            "n_questions": len(combined_q),
            "dataset": f"financebench_150+custom_verified_{len(custom_items)}",
            "mode": mode,
        }
        combined_path = RESULTS_DIR / f"eval_combined{suffix}_{ts}.json"
        combined_path.write_text(json.dumps(combined_output, indent=2))
        RESULTS_DIR.joinpath(f"latest_combined{suffix}.json").write_text(
            json.dumps(combined_output, indent=2)
        )
        print(f"\nCombined results ({len(combined_q)}Q): {combined_output}")
        print(f"Saved → {combined_path}")
    else:
        print(f"Saved → {RESULTS_DIR / f'eval{suffix}_{ts}.json'}")


if __name__ == "__main__":
    main()

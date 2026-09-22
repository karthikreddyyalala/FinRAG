"""Full 300-question eval runner. Outputs evals/results/eval_<timestamp>.json."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

RESULTS_DIR = Path(__file__).parent / "results"
FINANCEBENCH = Path(__file__).parent / "eval_data" / "financebench_150.json"
CUSTOM = Path(__file__).parent / "eval_data" / "custom_150.json"


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def _init_clients():
    import boto3
    from pinecone import Pinecone

    from pipeline.sync_pinecone import get_embed_fn, load_bm25_index
    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    pinecone_index = pc.Index("finrag-filings")
    s3 = boto3.client("s3", region_name="us-east-1")
    bm25_index, bm25_chunks = load_bm25_index(s3, "finrag-processed-filings", "bm25/index.pkl")
    embed_fn = get_embed_fn(bedrock)
    return bedrock, pinecone_index, bm25_index, bm25_chunks, embed_fn


def _call_pipeline(
    question: str, bedrock, pinecone_index, bm25_index, bm25_chunks, embed_fn
) -> dict:
    from server.mcp_tools.search_filings import build_search_filings_answer
    return build_search_filings_answer(
        query=question,
        bedrock_client=bedrock,
        pinecone_index=pinecone_index,
        bm25_index=bm25_index,
        bm25_chunks=bm25_chunks,
        embed_fn=embed_fn,
    )


def _run_dataset(
    items: list[dict], label: str, clients: tuple, checkpoint: Path
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
        result = _call_pipeline(question, *clients)
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


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    if not FINANCEBENCH.exists():
        print(f"ERROR: {FINANCEBENCH} not found.")
        sys.exit(1)

    print("Initializing clients (loading BM25 index from S3) ...")
    clients = _init_clients()

    fb_items = _load(FINANCEBENCH)
    print(f"Running full eval: {len(fb_items)} FinanceBench questions")

    checkpoint = RESULTS_DIR / "financebench_answers.json"
    q, a, c, g = _run_dataset(fb_items, "Q", clients, checkpoint)

    from evals.metrics.numerical_accuracy import numerical_accuracy
    from evals.metrics.ragas_metrics import score_dataset

    ragas_scores = score_dataset(q, a, c, g)
    num_acc = numerical_accuracy(a, c)

    output = {
        **ragas_scores,
        "numerical_accuracy": num_acc,
        "n_questions": len(q),
        "dataset": "financebench_150",
    }
    ts = int(time.time())
    out_path = RESULTS_DIR / f"eval_{ts}.json"
    out_path.write_text(json.dumps(output, indent=2))
    RESULTS_DIR.joinpath("latest.json").write_text(json.dumps(output, indent=2))
    print(f"\nFull eval results: {output}")
    print(f"Saved → {out_path}")


if __name__ == "__main__":
    main()

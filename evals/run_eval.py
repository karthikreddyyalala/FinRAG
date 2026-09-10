"""Full 300-question eval runner. Outputs evals/results/eval_<timestamp>.json."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

RESULTS_DIR = Path(__file__).parent / "results"
FINANCEBENCH = Path(__file__).parent / "datasets" / "financebench_150.json"
CUSTOM = Path(__file__).parent / "datasets" / "custom_150.json"


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text())


def _call_pipeline(question: str) -> dict:
    import boto3
    from pinecone import Pinecone
    from pipeline.sync_pinecone import load_bm25_index, get_embed_fn
    from server.mcp_tools.search_filings import build_search_filings_answer

    # ponytail: these clients are re-created per call; move outside loop if perf matters
    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    pinecone_index = pc.Index("finrag-filings")
    s3 = boto3.client("s3", region_name="us-east-1")
    bm25_index, bm25_chunks = load_bm25_index(s3, "finrag-processed-filings", "bm25/index.pkl")
    embed_fn = get_embed_fn(bedrock)

    return build_search_filings_answer(
        query=question,
        bedrock_client=bedrock,
        pinecone_index=pinecone_index,
        bm25_index=bm25_index,
        bm25_chunks=bm25_chunks,
        embed_fn=embed_fn,
    )


def _run_dataset(items: list[dict], label: str) -> tuple[list, list, list, list]:
    questions, answers, contexts, ground_truths = [], [], [], []
    for i, item in enumerate(items, 1):
        print(f"  [{label} {i}/{len(items)}] {item['question'][:80]}")
        result = _call_pipeline(item["question"])
        questions.append(item["question"])
        answers.append(result.get("answer", ""))
        contexts.append([c.get("text", "") for c in result.get("citations", [])])
        ground_truths.append(item.get("ground_truth", ""))
    return questions, answers, contexts, ground_truths


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    for p in [FINANCEBENCH, CUSTOM]:
        if not p.exists():
            print(f"ERROR: {p} not found.")
            sys.exit(1)

    fb_items = _load(FINANCEBENCH)
    cust_items = _load(CUSTOM)
    all_items = fb_items + cust_items
    print(f"Running full eval: {len(fb_items)} FinanceBench + {len(cust_items)} custom = {len(all_items)} total")

    q, a, c, g = _run_dataset(all_items, "Q")

    from evals.metrics.ragas_metrics import score_dataset
    from evals.metrics.numerical_accuracy import numerical_accuracy

    ragas_scores = score_dataset(q, a, c, g)
    num_acc = numerical_accuracy(a, c)

    output = {**ragas_scores, "numerical_accuracy": num_acc, "n_questions": len(q)}
    ts = int(time.time())
    out_path = RESULTS_DIR / f"eval_{ts}.json"
    out_path.write_text(json.dumps(output, indent=2))
    RESULTS_DIR.joinpath("latest.json").write_text(json.dumps(output, indent=2))
    print(f"\nFull eval results: {output}")
    print(f"Saved → {out_path}")


if __name__ == "__main__":
    main()

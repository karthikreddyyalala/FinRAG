"""CI eval runner: 30-question subset, outputs evals/results/ci_latest.json."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add project root so imports resolve without install
sys.path.insert(0, str(Path(__file__).parent.parent))

RESULTS_DIR = Path(__file__).parent / "results"
CI_DATASET = Path(__file__).parent / "datasets" / "financebench_150.json"
CI_SAMPLE = 30


def _load_questions(path: Path, n: int) -> list[dict]:
    items = json.loads(path.read_text())
    return items[:n]


def _call_pipeline(question: str) -> dict:
    """Call the search_filings pipeline. Returns {answer, contexts}."""
    import boto3
    from pinecone import Pinecone
    from pipeline.sync_pinecone import load_bm25_index, get_embed_fn
    from server.mcp_tools.search_filings import build_search_filings_answer

    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    pinecone_index = pc.Index("finrag-filings")

    s3 = boto3.client("s3", region_name="us-east-1")
    bm25_index, bm25_chunks = load_bm25_index(s3, "finrag-processed-filings", "bm25/index.pkl")
    embed_fn = get_embed_fn(bedrock)

    result = build_search_filings_answer(
        query=question,
        bedrock_client=bedrock,
        pinecone_index=pinecone_index,
        bm25_index=bm25_index,
        bm25_chunks=bm25_chunks,
        embed_fn=embed_fn,
    )
    return result


def main() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)

    if not CI_DATASET.exists():
        print(f"ERROR: {CI_DATASET} not found. Run scripts/download_financebench.py first.")
        sys.exit(1)

    questions_data = _load_questions(CI_DATASET, CI_SAMPLE)
    print(f"Running CI eval on {len(questions_data)} questions ...")

    questions, answers, contexts, ground_truths = [], [], [], []
    for i, item in enumerate(questions_data, 1):
        print(f"  [{i}/{len(questions_data)}] {item['question'][:80]}")
        result = _call_pipeline(item["question"])
        questions.append(item["question"])
        answers.append(result.get("answer", ""))
        contexts.append([c.get("text", "") for c in result.get("citations", [])])
        ground_truths.append(item.get("ground_truth", ""))

    from evals.metrics.ragas_metrics import score_dataset
    from evals.metrics.numerical_accuracy import numerical_accuracy

    ragas_scores = score_dataset(questions, answers, contexts, ground_truths)
    num_acc = numerical_accuracy(answers, contexts)

    output = {**ragas_scores, "numerical_accuracy": num_acc, "n_questions": len(questions)}
    RESULTS_DIR.joinpath("ci_latest.json").write_text(json.dumps(output, indent=2))
    print(f"\nCI Eval results: {output}")

    # Gate checks (same thresholds as CLAUDE.md Phase 4)
    assert output.get("faithfulness", 0) >= 0.85, (
        f"faithfulness {output.get('faithfulness')} < 0.85"
    )
    assert output.get("numerical_accuracy", 0) >= 0.90, (
        f"numerical_accuracy {output.get('numerical_accuracy')} < 0.90"
    )
    print("All CI gates passed.")


if __name__ == "__main__":
    main()

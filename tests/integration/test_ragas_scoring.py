"""TDD: score_dataset returns valid metric dict on a small real sample."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

CHECKPOINT = Path(__file__).parent.parent.parent / "evals/results/financebench_answers.json"
EXPECTED_KEYS = {"faithfulness", "answer_relevancy", "context_precision", "context_recall"}


def test_score_dataset_returns_valid_metrics_on_3_questions():
    """score_dataset must return a dict with 4 metric keys, each 0-1, on 3 questions."""
    assert CHECKPOINT.exists(), f"Checkpoint missing: {CHECKPOINT}"

    rows = json.loads(CHECKPOINT.read_text())[:3]
    assert len(rows) == 3, "Need at least 3 checkpointed answers"

    from evals.metrics.ragas_metrics import score_dataset

    result = score_dataset(
        questions=[r["question"] for r in rows],
        answers=[r["answer"] for r in rows],
        contexts=[r["contexts"] for r in rows],
        ground_truths=[r["ground_truth"] for r in rows],
    )

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    for key in EXPECTED_KEYS:
        assert key in result, f"Missing key: {key}"
        assert 0.0 <= result[key] <= 1.0, f"{key}={result[key]} out of range"

    print(f"PASS — scores: {result}")


if __name__ == "__main__":
    test_score_dataset_returns_valid_metrics_on_3_questions()

"""Why did BM25-only "beat" the full pipeline on numerical_accuracy?

Short answer: it didn't. numerical_accuracy scores an answer with no numbers
in it as a perfect 1.0 (see numerical_accuracy.py line ~55), so the metric is
maximised by refusing to answer. BM25-only retrieves the least useful context,
refuses the most, and therefore scores the highest.

Measured on actual correctness instead -- did the answer state the number the
ground truth says it should -- the ordering reverses and the full pipeline wins.

Run: PYTHONPATH=. python3 evals/analyze_baseline_gap.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from evals.metrics.numerical_accuracy import _extract_numbers, numerical_accuracy

RESULTS = Path(__file__).resolve().parent / "results"

RUNS = {
    "full": "financebench_answers.json",
    "bm25_only": "financebench_answers_bm25_only.json",
    "dense_only": "financebench_answers_dense_only.json",
}

_REFUSAL_PATTERNS = [
    r"does not (provide|include|contain|mention|specify)",
    r"cannot (determine|answer|calculate|be determined)",
    r"could not find",
    r"not (provided|available|included) in the (provided )?context",
    r"unavailable in retrieved",
    r"insufficient (information|context)",
    r"no information",
]
_REFUSAL_RE = re.compile("|".join(_REFUSAL_PATTERNS), re.IGNORECASE)


def is_refusal(answer: str) -> bool:
    """True if the answer declines rather than states a figure."""
    return bool(_REFUSAL_RE.search(answer))


def _significant_numbers(text: str, floor: float) -> list[float]:
    """Numbers above `floor`, to avoid matching bare years and small counts."""
    return [n for n in _extract_numbers(text) if abs(n) > floor]


def states_correct_number(
    answer: str, ground_truth: str, tol: float = 0.02, floor: float = 1.5
) -> bool | None:
    """Did the answer state a number matching the ground truth's?

    This is a deliberately crude correctness proxy, not an LLM judge. It can
    false-positive when an unrelated number in the answer happens to land
    within tolerance. It is used only to compare configurations against each
    other on the same questions, where that noise applies equally to all three.

    Returns None when the ground truth has no significant number to match on.
    """
    truth_numbers = _significant_numbers(ground_truth, floor)
    if not truth_numbers:
        return None
    answer_numbers = _significant_numbers(answer, floor)
    return any(
        abs(a - g) / max(abs(g), 1e-9) <= tol for g in truth_numbers for a in answer_numbers
    )


def main() -> None:
    runs = {name: json.loads((RESULTS / f).read_text()) for name, f in RUNS.items()}

    print("Refusal rate vs. the metric that supposedly ranks these configs")
    print(f"{'config':<12}{'refused':>10}{'answered':>10}{'num_accuracy':>14}")
    for name, rows in runs.items():
        refused = sum(is_refusal(r["answer"]) for r in rows)
        score = numerical_accuracy([r["answer"] for r in rows], [r["contexts"] for r in rows])
        print(
            f"{name:<12}{refused:>7}/150{150 - refused:>10}{score * 100:>13.1f}%"
        )
    print("\n  The config that refuses MOST scores HIGHEST. That is the artifact.\n")

    print("numerical_accuracy split by whether the question was actually answered")
    print(f"{'config':<12}{'answered':>18}{'refused':>18}")
    for name, rows in runs.items():
        answered = [r for r in rows if not is_refusal(r["answer"])]
        refused = [r for r in rows if is_refusal(r["answer"])]
        a = numerical_accuracy([r["answer"] for r in answered], [r["contexts"] for r in answered])
        r_ = numerical_accuracy([r["answer"] for r in refused], [r["contexts"] for r in refused])
        print(f"{name:<12}{a * 100:>16.1f}%{r_ * 100:>17.1f}%")
    print("\n  Refusals score near-perfectly because they state no numbers.\n")

    print("Correctness instead: did the answer state the ground truth's number?")
    print(f"{'config':<12}{'judgeable':>11}{'correct':>9}{'rate':>8}")
    for name, rows in runs.items():
        verdicts = [states_correct_number(r["answer"], r["ground_truth"]) for r in rows]
        judgeable = [v for v in verdicts if v is not None]
        correct = sum(judgeable)
        print(f"{name:<12}{len(judgeable):>11}{correct:>9}{correct / len(judgeable) * 100:>7.1f}%")
    print("\n  The ordering reverses: the full pipeline states the right number")
    print("  more often than BM25-only, which the groundedness metric hid.")


if __name__ == "__main__":
    main()

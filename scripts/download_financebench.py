"""Download FinanceBench JSONL and convert to evals/eval_data/financebench_150.json."""
import json
from pathlib import Path

import requests

URL = (
    "https://huggingface.co/datasets/PatronusAI/financebench/resolve/main/"
    "financebench_merged.jsonl"
)
OUT = Path(__file__).parent.parent / "evals" / "eval_data" / "financebench_150.json"


def main() -> None:
    print("Downloading FinanceBench from HuggingFace ...")
    resp = requests.get(URL, timeout=30)
    resp.raise_for_status()
    rows = [json.loads(line) for line in resp.text.strip().splitlines()]
    print(f"  {len(rows)} rows found")

    subset = [
        {
            "question": r["question"],
            "ground_truth": r["answer"],
            "ticker": r.get("company", ""),
            "filing_type": r.get("doc_type", ""),
            "period": r.get("doc_period", ""),
        }
        for r in rows[:150]
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(subset, indent=2))
    print(f"Saved {len(subset)} questions → {OUT}")


if __name__ == "__main__":
    main()

"""Download FinanceBench CSV and convert to evals/datasets/financebench_150.json."""
import csv
import json
import os
import sys
import urllib.request
from pathlib import Path

URL = (
    "https://raw.githubusercontent.com/patronusai/financebench/main/"
    "financebench_open_source.csv"
)
OUT = Path(__file__).parent.parent / "evals" / "datasets" / "financebench_150.json"


def main() -> None:
    print(f"Downloading FinanceBench from {URL} ...")
    with urllib.request.urlopen(URL) as resp:
        lines = resp.read().decode("utf-8").splitlines()

    reader = csv.DictReader(lines)
    rows = list(reader)
    print(f"  {len(rows)} rows found")

    # Take first 150; keep only the fields we need
    subset = [
        {
            "question": r["question"],
            "ground_truth": r["answer"],
            "ticker": r.get("ticker", ""),
            "filing_type": r.get("doc_type", ""),
            "period": r.get("period_of_report", ""),
        }
        for r in rows[:150]
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(subset, indent=2))
    print(f"Saved {len(subset)} questions → {OUT}")


if __name__ == "__main__":
    main()

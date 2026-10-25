"""Save the official FinanceBench question -> source document labels locally.

Run: PYTHONPATH=. python3 evals/fetch_financebench_docs.py
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

URL = (
    "https://raw.githubusercontent.com/patronus-ai/financebench/main/data/"
    "financebench_open_source.jsonl"
)
OUT = Path(__file__).resolve().parent / "eval_data" / "financebench_docs.json"


def parse_rows(raw: str) -> list[dict]:
    """Keep the fields the evals need from the official JSONL."""
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        rows.append({
            "question": r["question"],
            "doc_name": r["doc_name"],
            "company": r["company"],
            "evidence": [e.get("evidence_text", "") for e in r.get("evidence", [])],
            "ground_truth": r["answer"],
        })
    return rows


def main() -> None:
    raw = subprocess.run(
        ["curl", "-s", URL], capture_output=True, text=True, check=True
    ).stdout
    rows = parse_rows(raw)
    OUT.write_text(json.dumps(rows, indent=2))
    print(f"saved {len(rows)} rows, {len({r['doc_name'] for r in rows})} docs -> {OUT}")


if __name__ == "__main__":
    main()

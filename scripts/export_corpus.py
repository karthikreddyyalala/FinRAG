"""Write dashboard/data/corpus.json from the local index's coverage table.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/export_corpus.py
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from pipeline.sync_pinecone import KeywordIndex

INDEX = Path("evals/results/keyword_index.sqlite")
OUT = Path("dashboard/data/corpus.json")


def main() -> None:
    rows = KeywordIndex(INDEX).coverage()
    corpus = {
        "companies": len({r["ticker"] for r in rows}),
        "filings": len(rows),
        "chunks": sum(r["chunks"] for r in rows),
        "by_form": dict(sorted(Counter(r["filing_type"] for r in rows).items())),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": f"{INDEX} coverage table",
    }
    OUT.write_text(json.dumps(corpus, indent=2) + "\n")
    print(corpus)


if __name__ == "__main__":
    main()

"""Add chunk_lookup and coverage tables to an existing keyword index, in place.

The published index (s3://finrag-processed-filings/keyword/index.sqlite) was
built before build_keyword_index wrote these tables. Adding them reads the
file once instead of re-chunking the corpus. Old server code ignores the
extra tables, so uploading the upgraded file is safe before or after a deploy.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/upgrade_keyword_index.py PATH
    PYTHONPATH=. .venv/bin/python scripts/upgrade_keyword_index.py PATH --upload
"""
from __future__ import annotations

import sqlite3
import sys
import time

from pipeline.sync_pinecone import KeywordIndex, add_lookup_tables

BUCKET = "finrag-processed-filings"
KEY = "keyword/index.sqlite"


def main() -> None:
    args = sys.argv[1:]
    upload = "--upload" in args
    paths = [a for a in args if a != "--upload"]
    if len(paths) != 1:
        print(__doc__)
        sys.exit(1)
    path = paths[0]

    start = time.monotonic()
    conn = sqlite3.connect(path)
    add_lookup_tables(conn)
    ids = conn.execute("SELECT COUNT(*) FROM chunk_lookup").fetchone()[0]
    conn.close()
    filings = KeywordIndex(path).coverage()
    print(
        f"tables added in {time.monotonic() - start:.0f}s: "
        f"{len({f['ticker'] for f in filings})} companies, {len(filings)} filings, "
        f"{sum(f['chunks'] for f in filings)} chunks, {ids} unique ids"
    )

    if upload:
        import boto3

        boto3.client("s3").upload_file(path, BUCKET, KEY)  # multipart for large files
        print(f"uploaded to s3://{BUCKET}/{KEY}")


if __name__ == "__main__":
    main()

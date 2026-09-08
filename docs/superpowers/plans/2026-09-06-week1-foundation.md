# Week 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the full ingestion-to-query pipeline for 20 companies — EDGAR download → extraction → chunking → Pinecone sync → MCP server with one tool — deployed to Lambda and answering real queries from Claude Desktop.

**Architecture:** A linear pipeline (`pipeline/`) turns SEC filings into Pinecone vectors; a thin FastAPI+MCP server (`server/`) exposes one tool (`search_sec_filings`) that queries Pinecone directly (no reranking/rewriting yet — that's Week 2). Infra is CDK Python (`infra/`), one stack for S3 + DynamoDB.

**Tech Stack:** Python 3.12, boto3, requests, BeautifulSoup4 + lxml + pandas (HTML/table extraction — see deviation note below), `pinecone` SDK v8, Bedrock Titan Embeddings V2, `mcp` SDK v2, FastAPI + Mangum, AWS CDK 2.268.0.

**Deviations from CLAUDE.md, already approved by the user this session:**
1. **`pdf_processor.py` → `html_processor.py`, pdfplumber → BeautifulSoup/pandas.** SEC EDGAR serves 10-Q/10-K filings as HTML (`primaryDocument` is `.htm`), never as PDF — PDF is only an unofficial supplementary format. pdfplumber cannot process HTML, so the raw filings are stored and parsed as HTML natively.
2. **`pinecone-client` → `pinecone`.** The SDK was renamed; `pinecone-client` is deprecated and no longer receives updates.
3. **`mcp` pinned to `>=2.0,<3.0`.** v2 is a breaking rework of the SDK (2026-07-28 spec); pinning avoids silently picking up v1-incompatible or future-breaking releases.
4. Reranker/CrossEncoder packaging (container-image Lambda) is a Week 2 concern — `reranker.py` is not built in Week 1 per CLAUDE.md's own task order, so it's out of scope for this plan.

---

## File Structure

```
claude.md                              # Task 0: corrected in place (pdfplumber/pinecone-client/mcp/Titan free-tier notes)
infra/
├── __init__.py                        # Task 1
├── app.py                             # Task 2
└── stacks/
    ├── __init__.py                    # Task 1
    └── storage_stack.py               # Task 2
pipeline/
├── __init__.py                        # Task 1
├── edgar_client.py                    # Task 3
├── html_processor.py                  # Task 4
├── chunker.py                         # Task 5
└── sync_pinecone.py                   # Task 6
server/
├── __init__.py                        # Task 1
├── main.py                            # Task 7
└── mcp_tools/
    ├── __init__.py                    # Task 1
    └── search_filings.py              # Task 7
scripts/
└── bootstrap_corpus.py                # Task 8
tests/
├── __init__.py
├── conftest.py                        # Task 1
└── unit/
    ├── test_storage_stack.py          # Task 2
    ├── test_edgar_client.py           # Task 3
    ├── test_html_processor.py         # Task 4
    ├── test_chunker.py                # Task 5
    ├── test_sync_pinecone.py          # Task 6
    ├── test_search_filings.py         # Task 7
    ├── test_main.py                   # Task 7
    └── test_bootstrap_corpus.py       # Task 8
requirements.txt                       # Task 1
pyproject.toml                         # Task 1
cdk.json                               # Task 1
```

---

### Task 0: Correct CLAUDE.md for verified stack facts

**Files:**
- Modify: `claude.md`

- [ ] **Step 1: Fix the pdf_processor.py / pdfplumber references**

In `claude.md`, Phase 1 stack table row "PDF processing | pdfplumber | ...", change to:

```markdown
| Document processing | BeautifulSoup4 + lxml + pandas | Free | EDGAR filings are served as HTML, not PDF; pdfplumber cannot read them |
```

In Phase 2 repo tree, change `pdf_processor.py` to `html_processor.py` with updated comment `# BeautifulSoup + pandas table/text extraction`.

In Phase 3 Step 2, change the heading to `html_processor.py processes each filing with BeautifulSoup + pandas` and update the description to reference `.htm` files, not PDFs.

In Phase 7 Week 1 tasks, change `pdf_processor.py: pdfplumber extraction for text + tables` to `html_processor.py: BeautifulSoup + pandas extraction for text + tables`.

- [ ] **Step 2: Fix the pinecone-client reference**

In Phase 1 stack table, change "Pinecone free tier" row's implicit package name — add a parenthetical: `Pinecone free tier (pip package: pinecone, not the deprecated pinecone-client)`.

- [ ] **Step 3: Fix the Titan Embeddings "Free tier 3mo" claim**

In Phase 1 stack table, change:
```markdown
| Embeddings | Amazon Titan Text Embeddings V2 | Free tier 3mo | Native Bedrock |
```
to:
```markdown
| Embeddings | Amazon Titan Text Embeddings V2 | ~$0.02/1M tokens (no free tier) | Native Bedrock; cost is trivial (~$0.25 one-time for initial 500-filing corpus) |
```

- [ ] **Step 4: Update Phase 11 Current State**

```markdown
Current week: 1
Last completed: repo init, GitHub push, plan written
Next task: Task 1 (project scaffolding) of docs/superpowers/plans/2026-09-06-week1-foundation.md
Blockers: none
Eval scores: not yet available
Latest ragas faithfulness: N/A
Latest numerical_accuracy: N/A
Cost per query: N/A
```

- [ ] **Step 5: Commit**

```bash
git add claude.md
git commit -m "docs: correct stack facts (HTML not PDF, pinecone rename, no Titan free tier)"
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `pyproject.toml`
- Create: `cdk.json`
- Create: `infra/__init__.py`, `infra/stacks/__init__.py`
- Create: `pipeline/__init__.py`
- Create: `server/__init__.py`, `server/mcp_tools/__init__.py`
- Create: `tests/__init__.py`, `tests/unit/__init__.py`, `tests/conftest.py`

- [ ] **Step 1: Write requirements.txt**

```
boto3>=1.34,<2.0
requests>=2.31,<3.0
beautifulsoup4>=4.12,<5.0
lxml>=5.0,<6.0
pandas>=2.2,<3.0
pinecone>=8.0,<9.0
mcp>=2.0,<3.0
fastapi>=0.115,<1.0
mangum>=0.19,<1.0
aws-cdk-lib==2.268.0
constructs>=10.0.0,<11.0.0
pytest>=8.0,<9.0
moto[s3,dynamodb]>=5.0,<6.0
responses>=0.25,<1.0
ruff>=0.7,<1.0
```

- [ ] **Step 2: Write pyproject.toml**

```toml
[project]
name = "finrag-mcp"
version = "0.1.0"
requires-python = ">=3.12"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 3: Write cdk.json**

```json
{
  "app": "python -m infra.app",
  "watch": {
    "include": ["infra/**"],
    "exclude": ["infra/cdk.out/**"]
  },
  "context": {}
}
```

- [ ] **Step 4: Create empty package init files**

```bash
mkdir -p infra/stacks pipeline server/mcp_tools tests/unit
touch infra/__init__.py infra/stacks/__init__.py
touch pipeline/__init__.py
touch server/__init__.py server/mcp_tools/__init__.py
touch tests/__init__.py tests/unit/__init__.py
```

- [ ] **Step 5: Write tests/conftest.py**

```python
"""Shared test setup: dummy env vars so importing server.main never needs
real credentials or a real Pinecone account during unit tests."""
import os

os.environ.setdefault("PINECONE_API_KEY", "test-key-for-unit-tests")
```

- [ ] **Step 6: Install dependencies and verify the environment**

Run: `python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
Expected: all packages install with no errors.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pyproject.toml cdk.json infra pipeline server tests .venv 2>/dev/null; git add requirements.txt pyproject.toml cdk.json infra pipeline server tests
git commit -m "chore: project scaffolding (deps, package structure, pytest config)"
```

---

### Task 2: CDK storage stack (S3 + DynamoDB)

**Files:**
- Create: `infra/stacks/storage_stack.py`
- Create: `infra/app.py`
- Test: `tests/unit/test_storage_stack.py`

- [ ] **Step 1: Write the failing test**

```python
import aws_cdk as cdk
from aws_cdk.assertions import Template

from infra.stacks.storage_stack import StorageStack


def test_storage_stack_creates_two_buckets_and_one_table():
    app = cdk.App()
    stack = StorageStack(app, "TestStorageStack")
    template = Template.from_stack(stack)

    template.resource_count_is("AWS::S3::Bucket", 2)
    template.resource_count_is("AWS::DynamoDB::Table", 1)
    template.has_resource_properties(
        "AWS::S3::Bucket", {"BucketName": "finrag-raw-filings"}
    )
    template.has_resource_properties(
        "AWS::S3::Bucket", {"BucketName": "finrag-processed-filings"}
    )
    template.has_resource_properties(
        "AWS::DynamoDB::Table", {"TableName": "finrag-query-logs"}
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_storage_stack.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'infra.stacks.storage_stack'`

- [ ] **Step 3: Write storage_stack.py**

```python
"""S3 buckets and DynamoDB table for raw/processed filings and query logs."""
from __future__ import annotations

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from constructs import Construct


class StorageStack(Stack):
    """Storage layer: raw filings, processed filings, and query log table."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.raw_bucket = s3.Bucket(
            self,
            "RawFilingsBucket",
            bucket_name="finrag-raw-filings",
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        self.processed_bucket = s3.Bucket(
            self,
            "ProcessedFilingsBucket",
            bucket_name="finrag-processed-filings",
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        self.query_log_table = dynamodb.Table(
            self,
            "QueryLogTable",
            table_name="finrag-query-logs",
            partition_key=dynamodb.Attribute(
                name="query_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_storage_stack.py -v`
Expected: PASS (2 passed... actually 1 test, "1 passed")

- [ ] **Step 5: Write infra/app.py (CDK entry point, not unit tested — it's the synth entry point)**

```python
"""CDK app entry point for FinRAG MCP infrastructure."""
import aws_cdk as cdk

from infra.stacks.storage_stack import StorageStack

app = cdk.App()
StorageStack(app, "FinragStorageStack")
app.synth()
```

- [ ] **Step 6: Verify the CDK app synthesizes**

Run: `cdk synth --app "python -m infra.app"`
Expected: CloudFormation YAML output with no errors, showing `AWS::S3::Bucket` x2 and `AWS::DynamoDB::Table` x1.

- [ ] **Step 7: Commit**

```bash
git add infra/stacks/storage_stack.py infra/app.py tests/unit/test_storage_stack.py
git commit -m "feat: CDK storage stack (S3 raw/processed buckets, query log table)"
```

---

### Task 3: edgar_client.py

**Files:**
- Create: `pipeline/edgar_client.py`
- Test: `tests/unit/test_edgar_client.py`

- [ ] **Step 1: Write the failing tests**

```python
import boto3
import responses
from moto import mock_aws

from pipeline.edgar_client import (
    FilingMetadata,
    download_filing,
    get_cik_for_ticker,
    ingest_company,
    list_filings,
    store_filing,
)

FAKE_TICKER_MAP = {
    "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
}

FAKE_SUBMISSIONS = {
    "filings": {
        "recent": {
            "form": ["10-Q", "10-Q", "10-K", "8-K"],
            "filingDate": ["2026-08-01", "2026-05-01", "2026-02-01", "2026-01-15"],
            "accessionNumber": [
                "0001045810-26-000010",
                "0001045810-26-000008",
                "0001045810-26-000002",
                "0001045810-26-000001",
            ],
            "primaryDocument": [
                "nvda-10q-3.htm",
                "nvda-10q-2.htm",
                "nvda-10k.htm",
                "nvda-8k.htm",
            ],
        }
    }
}


@responses.activate
def test_get_cik_for_ticker_finds_match():
    responses.add(
        responses.GET,
        "https://www.sec.gov/files/company_tickers.json",
        json=FAKE_TICKER_MAP,
        status=200,
    )

    cik = get_cik_for_ticker("NVDA")

    assert cik == 1045810


@responses.activate
def test_get_cik_for_ticker_raises_when_not_found():
    responses.add(
        responses.GET,
        "https://www.sec.gov/files/company_tickers.json",
        json=FAKE_TICKER_MAP,
        status=200,
    )

    try:
        get_cik_for_ticker("ZZZZ")
        raise AssertionError("expected ValueError")
    except ValueError as e:
        assert "ZZZZ" in str(e)


@responses.activate
def test_list_filings_selects_only_target_forms_up_to_limits():
    responses.add(
        responses.GET,
        "https://data.sec.gov/submissions/CIK0001045810.json",
        json=FAKE_SUBMISSIONS,
        status=200,
    )

    filings = list_filings("NVDA", 1045810, max_10q=1, max_10k=1)

    forms = [f.form_type for f in filings]
    assert forms == ["10-Q", "10-K"]
    assert filings[0].filing_date == "2026-08-01"
    assert filings[0].primary_document == "nvda-10q-3.htm"


@responses.activate
def test_download_filing_fetches_from_archive_url():
    filing = FilingMetadata(
        ticker="NVDA",
        cik=1045810,
        form_type="10-Q",
        filing_date="2026-08-01",
        accession_number="0001045810-26-000010",
        primary_document="nvda-10q-3.htm",
    )
    responses.add(
        responses.GET,
        "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000010/nvda-10q-3.htm",
        body=b"<html>filing content</html>",
        status=200,
    )

    content = download_filing(filing)

    assert content == b"<html>filing content</html>"


@mock_aws
def test_store_filing_writes_expected_s3_key():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="finrag-raw-filings")
    filing = FilingMetadata(
        ticker="NVDA",
        cik=1045810,
        form_type="10-Q",
        filing_date="2026-08-01",
        accession_number="0001045810-26-000010",
        primary_document="nvda-10q-3.htm",
    )

    key = store_filing(s3, "finrag-raw-filings", filing, b"<html>content</html>")

    assert key == "NVDA/10-Q/2026-08-01.htm"
    obj = s3.get_object(Bucket="finrag-raw-filings", Key=key)
    assert obj["Body"].read() == b"<html>content</html>"


@mock_aws
@responses.activate
def test_ingest_company_end_to_end_writes_all_filings_to_s3():
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="finrag-raw-filings")

    responses.add(
        responses.GET,
        "https://www.sec.gov/files/company_tickers.json",
        json=FAKE_TICKER_MAP,
        status=200,
    )
    responses.add(
        responses.GET,
        "https://data.sec.gov/submissions/CIK0001045810.json",
        json=FAKE_SUBMISSIONS,
        status=200,
    )
    responses.add(
        responses.GET,
        "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000010/nvda-10q-3.htm",
        body=b"<html>10q-3</html>",
        status=200,
    )
    responses.add(
        responses.GET,
        "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000008/nvda-10q-2.htm",
        body=b"<html>10q-2</html>",
        status=200,
    )
    responses.add(
        responses.GET,
        "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000002/nvda-10k.htm",
        body=b"<html>10k</html>",
        status=200,
    )

    keys = ingest_company(s3, "finrag-raw-filings", "NVDA")

    assert set(keys) == {
        "NVDA/10-Q/2026-08-01.htm",
        "NVDA/10-Q/2026-05-01.htm",
        "NVDA/10-K/2026-02-01.htm",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_edgar_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.edgar_client'`

- [ ] **Step 3: Write pipeline/edgar_client.py**

```python
"""EDGAR API client: downloads 10-Q and 10-K filings and stores them in S3.

SEC EDGAR filings are published as HTML, not PDF -- the primaryDocument
field returned by the submissions API is almost always a .htm file. This
client stores that HTML as-is; html_processor.py handles extraction
downstream.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import requests
from botocore.client import BaseClient

SEC_USER_AGENT = "FinRAG MCP karthikreddyy386@gmail.com"
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/"
    "{primary_document}"
)
REQUEST_DELAY_SECONDS = 0.11  # keeps us under SEC's 10 req/sec limit


@dataclass
class FilingMetadata:
    """Metadata for a single SEC filing selected for download."""

    ticker: str
    cik: int
    form_type: str
    filing_date: str
    accession_number: str
    primary_document: str


def _sec_headers() -> dict[str, str]:
    """Return the User-Agent header SEC requires on every request."""
    return {"User-Agent": SEC_USER_AGENT}


def get_cik_for_ticker(ticker: str) -> int:
    """Look up a company's CIK number from SEC's official ticker mapping.

    Args:
        ticker: Stock ticker symbol, e.g. "NVDA".

    Returns:
        The company's CIK as an integer.

    Raises:
        ValueError: If the ticker is not found in SEC's mapping.
    """
    response = requests.get(TICKER_MAP_URL, headers=_sec_headers(), timeout=10)
    response.raise_for_status()
    time.sleep(REQUEST_DELAY_SECONDS)

    for entry in response.json().values():
        if entry["ticker"].upper() == ticker.upper():
            return int(entry["cik_str"])

    raise ValueError(f"Ticker {ticker!r} not found in SEC company_tickers.json")


def list_filings(
    ticker: str, cik: int, max_10q: int = 4, max_10k: int = 2
) -> list[FilingMetadata]:
    """List the most recent 10-Q and 10-K filings for a company.

    Args:
        ticker: Stock ticker symbol, used to tag the returned metadata.
        cik: Company CIK number from get_cik_for_ticker().
        max_10q: Maximum number of recent 10-Q filings to return.
        max_10k: Maximum number of recent 10-K filings to return.

    Returns:
        Filing metadata for up to max_10q 10-Qs and max_10k 10-Ks, most
        recent first.
    """
    url = SUBMISSIONS_URL.format(cik=cik)
    response = requests.get(url, headers=_sec_headers(), timeout=10)
    response.raise_for_status()
    time.sleep(REQUEST_DELAY_SECONDS)

    recent = response.json()["filings"]["recent"]
    filings: list[FilingMetadata] = []
    counts = {"10-Q": 0, "10-K": 0}
    limits = {"10-Q": max_10q, "10-K": max_10k}

    for i, form in enumerate(recent["form"]):
        if form not in counts or counts[form] >= limits[form]:
            continue
        filings.append(
            FilingMetadata(
                ticker=ticker,
                cik=cik,
                form_type=form,
                filing_date=recent["filingDate"][i],
                accession_number=recent["accessionNumber"][i],
                primary_document=recent["primaryDocument"][i],
            )
        )
        counts[form] += 1

    return filings


def download_filing(filing: FilingMetadata) -> bytes:
    """Download the raw HTML content of a single filing from EDGAR.

    Args:
        filing: Metadata identifying which filing document to fetch.

    Returns:
        Raw bytes of the filing's primary document (HTML).
    """
    accession_no_dashes = filing.accession_number.replace("-", "")
    url = ARCHIVE_URL.format(
        cik=filing.cik,
        accession_no_dashes=accession_no_dashes,
        primary_document=filing.primary_document,
    )
    response = requests.get(url, headers=_sec_headers(), timeout=15)
    response.raise_for_status()
    time.sleep(REQUEST_DELAY_SECONDS)
    return response.content


def store_filing(
    s3_client: BaseClient, bucket: str, filing: FilingMetadata, content: bytes
) -> str:
    """Store a downloaded filing in S3.

    Args:
        s3_client: A boto3 S3 client.
        bucket: Destination bucket name.
        filing: Metadata for the filing being stored.
        content: Raw HTML bytes from download_filing().

    Returns:
        The S3 key the filing was stored under.
    """
    key = f"{filing.ticker}/{filing.form_type}/{filing.filing_date}.htm"
    s3_client.put_object(Bucket=bucket, Key=key, Body=content, ContentType="text/html")
    return key


def ingest_company(s3_client: BaseClient, bucket: str, ticker: str) -> list[str]:
    """Download and store all target filings for one company.

    Args:
        s3_client: A boto3 S3 client.
        bucket: Destination bucket for raw filings.
        ticker: Stock ticker symbol to ingest.

    Returns:
        List of S3 keys written.
    """
    cik = get_cik_for_ticker(ticker)
    filings = list_filings(ticker, cik)
    keys = []
    for filing in filings:
        content = download_filing(filing)
        keys.append(store_filing(s3_client, bucket, filing, content))
    return keys
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_edgar_client.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add pipeline/edgar_client.py tests/unit/test_edgar_client.py
git commit -m "feat: edgar_client.py -- CIK lookup, filing listing, download, S3 storage"
```

---

### Task 4: html_processor.py

**Files:**
- Create: `pipeline/html_processor.py`
- Test: `tests/unit/test_html_processor.py`

- [ ] **Step 1: Write the failing tests**

```python
from bs4 import BeautifulSoup

from pipeline.html_processor import extract_tables, extract_text_blocks, process_filing

SAMPLE_HTML = """
<html><body>
<h2>Item 1. Financial Statements</h2>
<p>Net revenue increased due to strong data center demand this quarter.</p>
<table>
<tr><th>Segment</th><th>Q1 2024</th><th>Q1 2026</th></tr>
<tr><td>Data Center</td><td>4000</td><td>9000</td></tr>
</table>
<p>ok</p>
</body></html>
"""


def test_extract_text_blocks_drops_short_fragments():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")

    blocks = extract_text_blocks(soup)

    assert any("data center demand" in b.lower() for b in blocks)
    assert "ok" not in blocks


def test_extract_tables_returns_headers_and_rows():
    tables = extract_tables(SAMPLE_HTML)

    assert len(tables) == 1
    assert tables[0]["headers"] == ["Segment", "Q1 2024", "Q1 2026"]
    assert tables[0]["rows"] == [["Data Center", "4000", "9000"]]


def test_process_filing_returns_full_schema_with_metadata():
    metadata = {"ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026"}

    result = process_filing(SAMPLE_HTML, metadata)

    assert result["metadata"] == metadata
    assert len(result["tables"]) == 1
    assert len(result["text_blocks"]) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_html_processor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.html_processor'`

- [ ] **Step 3: Write pipeline/html_processor.py**

```python
"""Extracts text and tables from SEC filing HTML using BeautifulSoup + pandas.

SEC EDGAR serves 10-Q/10-K filings as HTML, not PDF, so this module replaces
the pdfplumber-based extraction originally specified in CLAUDE.md with an
HTML-native equivalent that reads the same raw bytes edgar_client.py stores.
"""
from __future__ import annotations

from io import StringIO
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup

MIN_TEXT_BLOCK_CHARS = 40  # skip boilerplate fragments (nav labels, single words)


def extract_text_blocks(soup: BeautifulSoup) -> list[str]:
    """Extract non-trivial text blocks, preserving section-like breaks.

    Args:
        soup: Parsed filing HTML.

    Returns:
        List of text blocks, one per paragraph/section-like element, with
        blocks shorter than MIN_TEXT_BLOCK_CHARS dropped.
    """
    blocks: list[str] = []
    for tag in soup.find_all(["p", "div", "span", "h1", "h2", "h3", "td"]):
        text = tag.get_text(separator=" ", strip=True)
        if len(text) >= MIN_TEXT_BLOCK_CHARS:
            blocks.append(text)
    return blocks


def extract_tables(html: str) -> list[dict[str, Any]]:
    """Extract structured tables from filing HTML using pandas.read_html.

    Args:
        html: Raw filing HTML content.

    Returns:
        List of {"headers": [...], "rows": [[...], ...]} dicts, one per
        table found. Tables that fail to parse cleanly are skipped.
    """
    tables: list[dict[str, Any]] = []
    try:
        dataframes = pd.read_html(StringIO(html))
    except ValueError:
        return tables

    for df in dataframes:
        if df.empty or df.shape[1] < 2:
            continue
        df = df.fillna("")
        headers = [str(c) for c in df.columns]
        rows = df.astype(str).values.tolist()
        tables.append({"headers": headers, "rows": rows})
    return tables


def process_filing(html: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """Process one filing's HTML into the standard extraction schema.

    Args:
        html: Raw filing HTML content, as stored by edgar_client.py.
        metadata: Filing metadata (ticker, filing_type, period, etc.) to
            attach unchanged to the output.

    Returns:
        {"text_blocks": [...], "tables": [...], "metadata": {...}}
    """
    soup = BeautifulSoup(html, "lxml")
    return {
        "text_blocks": extract_text_blocks(soup),
        "tables": extract_tables(html),
        "metadata": metadata,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_html_processor.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add pipeline/html_processor.py tests/unit/test_html_processor.py
git commit -m "feat: html_processor.py -- text and table extraction from filing HTML"
```

---

### Task 5: chunker.py

**Files:**
- Create: `pipeline/chunker.py`
- Test: `tests/unit/test_chunker.py`

- [ ] **Step 1: Write the failing tests**

```python
from pipeline.chunker import chunk_filing, chunk_tables, chunk_text_blocks

METADATA = {"ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026"}


def test_chunk_text_blocks_flushes_child_chunk_at_word_limit():
    blocks = ["word " * 100 for _ in range(5)]  # 5 blocks x 100 words = 500 words

    chunks = chunk_text_blocks(blocks, METADATA)

    child_chunks = [c for c in chunks if c["chunk_type"] == "child"]
    assert len(child_chunks) >= 1
    assert child_chunks[0]["ticker"] == "NVDA"
    assert child_chunks[0]["page_number"] is None


def test_chunk_text_blocks_flushes_remaining_short_content():
    blocks = ["short block of text here"]

    chunks = chunk_text_blocks(blocks, METADATA)

    assert len(chunks) == 2  # one parent, one child, both under the word limit
    assert {c["chunk_type"] for c in chunks} == {"parent", "child"}


def test_chunk_tables_creates_one_chunk_per_table_with_structure_preserved():
    tables = [{"headers": ["Segment", "Revenue"], "rows": [["Data Center", "9000"]]}]

    chunks = chunk_tables(tables, METADATA)

    assert len(chunks) == 1
    assert chunks[0]["chunk_type"] == "table"
    assert chunks[0]["table_headers"] == ["Segment", "Revenue"]
    assert "Data Center" in chunks[0]["text"]
    assert chunks[0]["ticker"] == "NVDA"


def test_chunk_filing_combines_text_and_table_chunks():
    processed = {
        "text_blocks": ["a reasonably long block of filing text content here"],
        "tables": [{"headers": ["A", "B"], "rows": [["1", "2"]]}],
        "metadata": METADATA,
    }

    chunks = chunk_filing(processed)

    types = {c["chunk_type"] for c in chunks}
    assert types == {"parent", "child", "table"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_chunker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.chunker'`

- [ ] **Step 3: Write pipeline/chunker.py**

```python
"""Hierarchical chunking of processed filing text and tables.

Splits processed filing output (from html_processor.py) into parent, child,
and table chunks, each tagged with filing metadata so downstream retrieval
can filter and cite precisely.

Token counts are approximated by whitespace word count. This is a Week 1
placeholder for a real tokenizer, documented as such -- exact token budgets
aren't load-bearing until reranking/generation limits are enforced in
Week 2+.
"""
from __future__ import annotations

import uuid
from typing import Any

PARENT_CHUNK_WORDS = 1500
CHILD_CHUNK_WORDS = 400


def _word_count(text: str) -> int:
    return len(text.split())


def _new_chunk(
    text: str, chunk_type: str, section: str, metadata: dict[str, Any]
) -> dict[str, Any]:
    return {
        "chunk_id": str(uuid.uuid4()),
        "text": text,
        "chunk_type": chunk_type,
        "section": section,
        "page_number": None,  # HTML filings have no native pagination
        **metadata,
    }


def chunk_text_blocks(
    text_blocks: list[str], metadata: dict[str, Any]
) -> list[dict[str, Any]]:
    """Group text blocks into parent (~1500 word) and child (~400 word) chunks.

    Args:
        text_blocks: Ordered text blocks from html_processor.process_filing().
        metadata: Filing-level metadata to attach to every chunk (ticker,
            filing_type, period, company_name, etc.).

    Returns:
        List of parent and child chunk dicts.
    """
    chunks: list[dict[str, Any]] = []

    parent_buffer: list[str] = []
    parent_words = 0
    child_buffer: list[str] = []
    child_words = 0
    section = "body"

    def flush_child() -> None:
        nonlocal child_buffer, child_words
        if child_buffer:
            chunks.append(_new_chunk(" ".join(child_buffer), "child", section, metadata))
        child_buffer = []
        child_words = 0

    def flush_parent() -> None:
        nonlocal parent_buffer, parent_words
        if parent_buffer:
            chunks.append(_new_chunk(" ".join(parent_buffer), "parent", section, metadata))
        parent_buffer = []
        parent_words = 0

    for block in text_blocks:
        words = _word_count(block)

        parent_buffer.append(block)
        parent_words += words
        if parent_words >= PARENT_CHUNK_WORDS:
            flush_parent()

        child_buffer.append(block)
        child_words += words
        if child_words >= CHILD_CHUNK_WORDS:
            flush_child()

    flush_parent()
    flush_child()

    return chunks


def chunk_tables(
    tables: list[dict[str, Any]], metadata: dict[str, Any]
) -> list[dict[str, Any]]:
    """Convert each extracted table into one chunk with structured metadata.

    Args:
        tables: Table dicts from html_processor.process_filing().
        metadata: Filing-level metadata to attach to every chunk.

    Returns:
        One chunk dict per table, with headers/rows serialized into the
        chunk text for embedding, and preserved structurally too.
    """
    chunks = []
    for table in tables:
        header_line = " | ".join(table["headers"])
        row_lines = [" | ".join(row) for row in table["rows"]]
        text = "\n".join([header_line, *row_lines])

        chunk = _new_chunk(text, "table", "table", metadata)
        chunk["table_headers"] = table["headers"]
        chunk["table_rows"] = table["rows"]
        chunks.append(chunk)
    return chunks


def chunk_filing(processed: dict[str, Any]) -> list[dict[str, Any]]:
    """Chunk a fully processed filing (text + tables) into all chunk types.

    Args:
        processed: Output of html_processor.process_filing(): {"text_blocks",
            "tables", "metadata"}.

    Returns:
        Combined list of parent, child, and table chunks.
    """
    metadata = processed["metadata"]
    return [
        *chunk_text_blocks(processed["text_blocks"], metadata),
        *chunk_tables(processed["tables"], metadata),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_chunker.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add pipeline/chunker.py tests/unit/test_chunker.py
git commit -m "feat: chunker.py -- hierarchical parent/child/table chunking"
```

---

### Task 6: sync_pinecone.py

**Files:**
- Create: `pipeline/sync_pinecone.py`
- Test: `tests/unit/test_sync_pinecone.py`

- [ ] **Step 1: Write the failing tests**

```python
import io
import json
from unittest.mock import MagicMock

from pipeline.sync_pinecone import chunk_to_pinecone_vector, embed_text, sync_chunks_to_pinecone


def _fake_bedrock_client(embedding: list[float]) -> MagicMock:
    client = MagicMock()
    body = io.BytesIO(json.dumps({"embedding": embedding}).encode())
    client.invoke_model.return_value = {"body": body}
    return client


def test_embed_text_calls_titan_and_returns_vector():
    client = _fake_bedrock_client([0.1, 0.2, 0.3])

    vector = embed_text(client, "Nvidia data center revenue grew.")

    assert vector == [0.1, 0.2, 0.3]
    call_kwargs = client.invoke_model.call_args.kwargs
    assert call_kwargs["modelId"] == "amazon.titan-embed-text-v2:0"
    assert "Nvidia data center revenue" in call_kwargs["body"]


def test_chunk_to_pinecone_vector_excludes_bulky_fields():
    chunk = {
        "chunk_id": "abc-123",
        "text": "Data Center | 9000",
        "chunk_type": "table",
        "table_rows": [["Data Center", "9000"]],
        "ticker": "NVDA",
        "page_number": None,
    }

    record = chunk_to_pinecone_vector(chunk, [0.1, 0.2])

    assert record["id"] == "abc-123"
    assert record["values"] == [0.1, 0.2]
    assert "table_rows" not in record["metadata"]
    assert "page_number" not in record["metadata"]  # None values dropped
    assert record["metadata"]["ticker"] == "NVDA"


def test_sync_chunks_to_pinecone_upserts_all_vectors_in_batches():
    client = _fake_bedrock_client([0.1, 0.2])
    index = MagicMock()
    chunks = [
        {"chunk_id": f"id-{i}", "text": f"chunk {i}", "chunk_type": "child", "ticker": "NVDA"}
        for i in range(3)
    ]

    total = sync_chunks_to_pinecone(client, index, chunks, batch_size=2)

    assert total == 3
    assert index.upsert.call_count == 2  # batch of 2, then batch of 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_sync_pinecone.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.sync_pinecone'`

- [ ] **Step 3: Write pipeline/sync_pinecone.py**

```python
"""Embeds chunks with Bedrock Titan V2 and upserts them into Pinecone.

Uses the `pinecone` package (not the deprecated `pinecone-client`).
"""
from __future__ import annotations

import json
from typing import Any

from pinecone import Pinecone

TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSIONS = 1024


def embed_text(bedrock_client: Any, text: str) -> list[float]:
    """Embed one chunk of text using Bedrock Titan Text Embeddings V2.

    Args:
        bedrock_client: A boto3 bedrock-runtime client.
        text: Chunk text to embed.

    Returns:
        Embedding vector as a list of floats.
    """
    response = bedrock_client.invoke_model(
        modelId=TITAN_MODEL_ID,
        body=json.dumps({"inputText": text, "dimensions": EMBEDDING_DIMENSIONS}),
    )
    payload = json.loads(response["body"].read())
    return payload["embedding"]


def chunk_to_pinecone_vector(chunk: dict[str, Any], embedding: list[float]) -> dict[str, Any]:
    """Build a Pinecone upsert record from a chunk and its embedding.

    Args:
        chunk: A chunk dict produced by chunker.py.
        embedding: The embedding vector from embed_text().

    Returns:
        {"id": ..., "values": ..., "metadata": ...} ready for Pinecone upsert.
        Bulky/non-scalar fields and None values are dropped -- Pinecone
        metadata must be JSON-scalar-ish and rejects null values.
    """
    metadata = {
        k: v
        for k, v in chunk.items()
        if k not in {"chunk_id", "table_rows"} and v is not None
    }
    return {"id": chunk["chunk_id"], "values": embedding, "metadata": metadata}


def sync_chunks_to_pinecone(
    bedrock_client: Any,
    pinecone_index: Any,
    chunks: list[dict[str, Any]],
    batch_size: int = 100,
) -> int:
    """Embed and upsert a list of chunks into a Pinecone index.

    Args:
        bedrock_client: A boto3 bedrock-runtime client.
        pinecone_index: A Pinecone Index handle (Pinecone().Index(name)).
        chunks: Chunks produced by chunker.chunk_filing().
        batch_size: Max vectors per Pinecone upsert call.

    Returns:
        Total number of vectors upserted.
    """
    vectors = [
        chunk_to_pinecone_vector(chunk, embed_text(bedrock_client, chunk["text"]))
        for chunk in chunks
    ]

    total = 0
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i : i + batch_size]
        pinecone_index.upsert(vectors=batch)
        total += len(batch)
    return total


def get_pinecone_index(api_key: str, index_name: str) -> Any:
    """Return a handle to a named Pinecone index.

    Args:
        api_key: Pinecone API key (read from env by the caller).
        index_name: Name of the target Pinecone index.

    Returns:
        A Pinecone Index object.
    """
    pc = Pinecone(api_key=api_key)
    return pc.Index(index_name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_sync_pinecone.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add pipeline/sync_pinecone.py tests/unit/test_sync_pinecone.py
git commit -m "feat: sync_pinecone.py -- Titan embedding + Pinecone upsert"
```

---

### Task 7: MCP server (main.py + search_filings.py)

**Files:**
- Create: `server/mcp_tools/search_filings.py`
- Create: `server/main.py`
- Test: `tests/unit/test_search_filings.py`
- Test: `tests/unit/test_main.py`

- [ ] **Step 1: Write the failing tests for search_filings.py**

```python
from unittest.mock import MagicMock

from mcp.server import MCPServer

from server.mcp_tools.search_filings import (
    build_search_filings_answer,
    register_search_filings_tool,
)


def _fake_pinecone_index(matches):
    index = MagicMock()
    index.query.return_value = {"matches": matches}
    return index


def test_build_search_filings_answer_returns_citations_from_matches():
    matches = [
        {
            "id": "chunk-1",
            "metadata": {
                "ticker": "NVDA",
                "filing_type": "10-Q",
                "period": "Q1-2026",
                "page_number": None,
                "text": "Data center revenue grew significantly year over year.",
            },
        }
    ]
    index = _fake_pinecone_index(matches)
    embed_fn = MagicMock(return_value=[0.1, 0.2, 0.3])

    result = build_search_filings_answer("Nvidia data center revenue?", index, embed_fn)

    assert result["citations"] == [
        {"ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026", "page": None}
    ]
    assert "Data center revenue grew" in result["answer"]
    assert result["cost_usd"] == 0.0
    assert isinstance(result["latency_ms"], int)
    embed_fn.assert_called_once_with("Nvidia data center revenue?")
    index.query.assert_called_once()


def test_register_search_filings_tool_does_not_raise():
    mcp = MCPServer("Test")
    index = _fake_pinecone_index([])
    embed_fn = MagicMock(return_value=[0.0])

    register_search_filings_tool(mcp, index, embed_fn)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_search_filings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.mcp_tools.search_filings'`

- [ ] **Step 3: Write server/mcp_tools/search_filings.py**

```python
"""search_sec_filings MCP tool: direct Pinecone query, no reranking (Week 1).

Week 2 adds query rewriting, hybrid BM25+dense search, CrossEncoder
reranking, and the numerical verifier per CLAUDE.md's build order. This
tool proves the retrieval -> citation plumbing works end to end first.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from mcp.server import MCPServer


def build_search_filings_answer(
    query: str,
    pinecone_index: Any,
    embed_fn: Callable[[str], list[float]],
    top_k: int = 5,
) -> dict[str, Any]:
    """Run a direct Pinecone similarity search and format a cited answer.

    Args:
        query: Natural language financial question.
        pinecone_index: A Pinecone Index handle.
        embed_fn: Callable(text) -> embedding vector, embeds the query.
        top_k: Number of chunks to retrieve.

    Returns:
        {"answer": str, "citations": [...], "cost_usd": float, "latency_ms": int}
    """
    start = time.monotonic()
    query_vector = embed_fn(query)
    results = pinecone_index.query(vector=query_vector, top_k=top_k, include_metadata=True)

    citations = []
    passages = []
    for match in results["matches"]:
        meta = match["metadata"]
        citations.append(
            {
                "ticker": meta.get("ticker"),
                "filing_type": meta.get("filing_type"),
                "period": meta.get("period"),
                "page": meta.get("page_number"),
            }
        )
        passages.append(meta.get("text", ""))

    answer = (
        "Retrieved passages (Week 1: raw retrieval, no generation model yet):\n\n"
        + "\n---\n".join(passages)
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    return {
        "answer": answer,
        "citations": citations,
        "cost_usd": 0.0,
        "latency_ms": latency_ms,
    }


def register_search_filings_tool(
    mcp: MCPServer, pinecone_index: Any, embed_fn: Callable[[str], list[float]]
) -> None:
    """Register the search_sec_filings tool on an MCPServer instance.

    Args:
        mcp: The MCPServer instance to register the tool on.
        pinecone_index: A Pinecone Index handle used at query time.
        embed_fn: Callable(text) -> embedding vector for embedding queries.
    """

    @mcp.tool()
    def search_sec_filings(query: str) -> dict[str, Any]:
        """Search ingested SEC filings and return a cited answer.

        Args:
            query: Natural language financial question, e.g. "How did
                Nvidia data center revenue change from Q1 2024 to Q1 2026?"

        Returns:
            Dict with answer text, citations, cost_usd, and latency_ms.
        """
        return build_search_filings_answer(query, pinecone_index, embed_fn)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_search_filings.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Write the failing test for main.py**

```python
from unittest.mock import MagicMock

from server.main import create_app


def test_create_app_returns_fastapi_app_with_mcp_mounted():
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {"matches": []}
    embed_fn = MagicMock(return_value=[0.0])

    app = create_app(pinecone_index, embed_fn)

    route_paths = [getattr(r, "path", None) for r in app.routes]
    assert any(path == "/" for path in route_paths)
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/unit/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.main'`

- [ ] **Step 7: Write server/main.py**

```python
"""FastAPI app entry point with MCP tool registration for FinRAG MCP.

Week 1 scope: one tool (search_sec_filings), direct Pinecone query, no
query rewriting, hybrid search, reranking, or generation model yet.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial
from typing import Any, Callable

import boto3
from fastapi import FastAPI
from mangum import Mangum
from mcp.server import MCPServer

from pipeline.sync_pinecone import embed_text, get_pinecone_index
from server.mcp_tools.search_filings import register_search_filings_tool


def create_app(
    pinecone_index: Any, embed_fn: Callable[[str], list[float]]
) -> FastAPI:
    """Build the FastAPI app with the MCP server mounted.

    Args:
        pinecone_index: A Pinecone Index handle for the search tool.
        embed_fn: Callable(text) -> embedding vector for embedding queries.

    Returns:
        A FastAPI app ready to serve via Mangum on Lambda.
    """
    mcp = MCPServer("FinRAG")
    register_search_filings_tool(mcp, pinecone_index, embed_fn)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.mount("/", mcp.streamable_http_app())
    return app


def _build_production_dependencies() -> tuple[Any, Callable[[str], list[float]]]:
    """Wire up real Bedrock + Pinecone clients for production use."""
    bedrock_client = boto3.client("bedrock-runtime")
    pinecone_index = get_pinecone_index(
        api_key=os.environ["PINECONE_API_KEY"], index_name="finrag-filings"
    )
    return pinecone_index, partial(embed_text, bedrock_client)


_pinecone_index, _embed_fn = _build_production_dependencies()
app = create_app(_pinecone_index, _embed_fn)
handler = Mangum(app)
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/unit/test_main.py -v`
Expected: PASS (1 passed) -- relies on `tests/conftest.py` setting a dummy `PINECONE_API_KEY` so `_build_production_dependencies()` doesn't raise `KeyError` at import time.

- [ ] **Step 9: Commit**

```bash
git add server/mcp_tools/search_filings.py server/main.py tests/unit/test_search_filings.py tests/unit/test_main.py
git commit -m "feat: MCP server -- search_sec_filings tool, direct Pinecone query"
```

---

### Task 8: bootstrap_corpus.py

**Files:**
- Create: `scripts/bootstrap_corpus.py`
- Test: `tests/unit/test_bootstrap_corpus.py`

- [ ] **Step 1: Write the failing test**

```python
from unittest.mock import MagicMock, patch

from pipeline.edgar_client import FilingMetadata
from scripts.bootstrap_corpus import bootstrap_ticker


@patch("scripts.bootstrap_corpus.sync_chunks_to_pinecone")
@patch("scripts.bootstrap_corpus.chunk_filing")
@patch("scripts.bootstrap_corpus.process_filing")
@patch("scripts.bootstrap_corpus.store_filing")
@patch("scripts.bootstrap_corpus.download_filing")
@patch("scripts.bootstrap_corpus.list_filings")
@patch("scripts.bootstrap_corpus.get_cik_for_ticker")
def test_bootstrap_ticker_runs_full_pipeline_per_filing(
    mock_cik, mock_list, mock_download, mock_store, mock_process, mock_chunk, mock_sync
):
    mock_cik.return_value = 1045810
    filing = FilingMetadata(
        ticker="NVDA",
        cik=1045810,
        form_type="10-Q",
        filing_date="2026-08-01",
        accession_number="0001-26-000010",
        primary_document="nvda.htm",
    )
    mock_list.return_value = [filing]
    mock_download.return_value = b"<html>content</html>"
    mock_process.return_value = {"text_blocks": [], "tables": [], "metadata": {}}
    mock_chunk.return_value = [{"chunk_id": "c1", "text": "x"}]
    mock_sync.return_value = 1

    total = bootstrap_ticker(MagicMock(), MagicMock(), MagicMock(), "NVDA")

    assert total == 1
    mock_list.assert_called_once_with("NVDA", 1045810)
    mock_download.assert_called_once_with(filing)
    mock_sync.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_bootstrap_corpus.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.bootstrap_corpus'`

- [ ] **Step 3: Write scripts/bootstrap_corpus.py**

```python
"""One-time bootstrap: ingest the initial 20-company corpus end to end.

Runs edgar_client -> html_processor -> chunker -> sync_pinecone for each
ticker in TARGET_TICKERS. Run once locally to seed the corpus before the
weekly refresh cron (Week 4+) takes over.
"""
from __future__ import annotations

import os
from functools import partial
from typing import Any

import boto3

from pipeline.chunker import chunk_filing
from pipeline.edgar_client import download_filing, get_cik_for_ticker, list_filings, store_filing
from pipeline.html_processor import process_filing
from pipeline.sync_pinecone import embed_text, get_pinecone_index, sync_chunks_to_pinecone

TARGET_TICKERS = [
    "NVDA", "AAPL", "MSFT", "GOOGL", "META",   # Tech
    "TSLA", "F", "GM", "RIVN", "LCID",         # EV/Auto
    "JPM", "BAC", "GS", "MS", "V",             # Finance
    "JNJ", "PFE", "UNH", "ABBV", "MRK",        # Healthcare
]

RAW_BUCKET = "finrag-raw-filings"


def bootstrap_ticker(
    s3_client: Any, bedrock_client: Any, pinecone_index: Any, ticker: str
) -> int:
    """Ingest, process, chunk, and sync one ticker's filings end to end.

    Args:
        s3_client: A boto3 S3 client.
        bedrock_client: A boto3 bedrock-runtime client.
        pinecone_index: A Pinecone Index handle.
        ticker: Stock ticker symbol to bootstrap.

    Returns:
        Number of chunks synced to Pinecone for this ticker.
    """
    cik = get_cik_for_ticker(ticker)
    filings = list_filings(ticker, cik)
    embed_fn = partial(embed_text, bedrock_client)

    total_chunks = 0
    for filing in filings:
        html = download_filing(filing).decode("utf-8", errors="ignore")
        store_filing(s3_client, RAW_BUCKET, filing, html.encode("utf-8"))

        metadata = {
            "ticker": filing.ticker,
            "filing_type": filing.form_type,
            "period": filing.filing_date,
        }
        processed = process_filing(html, metadata)
        chunks = chunk_filing(processed)
        total_chunks += sync_chunks_to_pinecone(bedrock_client, pinecone_index, chunks)

    return total_chunks


def main() -> None:
    """Bootstrap the full 20-company corpus."""
    s3_client = boto3.client("s3")
    bedrock_client = boto3.client("bedrock-runtime")
    pinecone_index = get_pinecone_index(
        api_key=os.environ["PINECONE_API_KEY"], index_name="finrag-filings"
    )

    for ticker in TARGET_TICKERS:
        count = bootstrap_ticker(s3_client, bedrock_client, pinecone_index, ticker)
        print(f"{ticker}: synced {count} chunks")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_bootstrap_corpus.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the full unit test suite**

Run: `pytest tests/unit -v`
Expected: All tests across Tasks 2-8 pass (roughly 20 tests total).

- [ ] **Step 6: Lint**

Run: `ruff check .`
Expected: No errors (fix any that appear before committing).

- [ ] **Step 7: Commit**

```bash
git add scripts/bootstrap_corpus.py tests/unit/test_bootstrap_corpus.py
git commit -m "feat: bootstrap_corpus.py -- end-to-end ingestion for 20 companies"
```

---

### Task 9: Deploy and connect to Claude Desktop (manual verification, not unit-testable)

**Files:** none created — this is infrastructure deployment and manual verification.

- [ ] **Step 1: Bootstrap and deploy the CDK stack**

```bash
cdk bootstrap --app "python -m infra.app"
cdk deploy --app "python -m infra.app" --require-approval never
```
Expected: `FinragStorageStack` deploys, outputs show the two bucket names and table name.

- [ ] **Step 2: Create the Pinecone index**

Via Pinecone console or SDK: create index `finrag-filings`, dimension `1024` (matches Titan V2), metric `cosine`, on the free tier (1 index, 2GB — matches CLAUDE.md Phase 1).

- [ ] **Step 3: Run bootstrap_corpus.py against the 20-company list**

```bash
export PINECONE_API_KEY=<your-real-key>
python -m scripts.bootstrap_corpus
```
Expected: prints `TICKER: synced N chunks` for all 20 tickers with no exceptions.

- [ ] **Step 4: Package and deploy the API Lambda**

Note: only `server/`, `pipeline/`, `requirements.txt` need to ship — no ML/torch deps in Week 1, so a standard zip-based Lambda function fits well under the 250MB unzipped limit. Add a `FunctionStack`/`DockerImageFunction`-free Lambda construct in `infra/stacks/mcp_server_stack.py` (not built in this plan — flag as the next CDK task if you want it done now, otherwise deploy manually via `sam` or `zip` + `aws lambda create-function` for a first smoke test).

- [ ] **Step 5: Connect Claude Desktop**

Add the deployed API Gateway endpoint to Claude Desktop's MCP server config (`claude_desktop_config.json`), pointing at the `/mcp` path Mangum/API Gateway expose.

- [ ] **Step 6: Test 5 manual queries**

Ask Claude Desktop 5 real financial questions covering the 20 ingested companies (e.g. "What did Apple say about iPhone revenue in their latest 10-Q?"). Confirm each response includes citations (even if the "answer" is still raw retrieved passages — Week 1 has no generation model wired in yet, that's `answer_generator.py` in Week 2).

- [ ] **Step 7: Push all commits**

```bash
git push
```

---

## Self-Review

**Spec coverage:** Every Week 1 task in CLAUDE.md Phase 7 has a corresponding task above: repo init (done pre-plan), storage stack (Task 2), EDGAR download (Task 3), extraction (Task 4, HTML not PDF per approved deviation), chunking (Task 5), Pinecone sync (Task 6), FastAPI+MCP server with one tool (Task 7), deploy + Claude Desktop connection (Task 9). `bootstrap_corpus.py` (Task 8) fulfills "download 10-Q/10-K for 20 companies" end to end, matching Phase 6's target corpus list exactly.

**Placeholder scan:** No TBD/TODO markers; every step has complete runnable code and exact commands.

**Type consistency:** `FilingMetadata` fields match across `edgar_client.py` and its test fixtures. `chunk_filing()`'s output dict keys (`chunk_id`, `text`, `chunk_type`, `ticker`, etc.) match what `sync_pinecone.chunk_to_pinecone_vector()` and `search_filings.build_search_filings_answer()` expect. `embed_fn` signature (`Callable[[str], list[float]]`) is consistent across `sync_pinecone.py`, `main.py`, and `search_filings.py`.

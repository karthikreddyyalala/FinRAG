"""EDGAR API client: downloads 10-Q and 10-K filings and stores them in S3.

SEC EDGAR filings are published as HTML, not PDF -- the primaryDocument
field returned by the submissions API is almost always a .htm file. This
client stores that HTML as-is; html_processor.py handles extraction
downstream.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

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


MAX_NETWORK_RETRIES = 5


def _get_with_retry(url: str, timeout: int = 15) -> Any:
    """GET a SEC URL, retrying transient network failures with backoff.

    A corpus build makes hundreds of sequential requests over tens of
    minutes, so a momentary DNS or connection blip is near-certain. Without
    this, one blip fails every remaining ticker and the run finishes by
    rebuilding the BM25 index over only the companies it reached -- quietly
    shrinking the corpus rather than erroring.

    Only connection-level faults are retried. An HTTP error status is a real
    answer, not a fault, and retrying it just burns SEC's rate limit.
    """
    delay = 2.0
    for attempt in range(MAX_NETWORK_RETRIES):
        try:
            response = requests.get(url, headers=_sec_headers(), timeout=timeout)
            response.raise_for_status()
            return response
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            if attempt == MAX_NETWORK_RETRIES - 1:
                raise
            print(f"    network blip, retrying in {delay:.0f}s ...", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 30)
    raise RuntimeError("unreachable")


# company_tickers.json lists only CURRENT registrants, so a company that was
# acquired or renamed disappears from it -- while every 10-K and 10-Q it ever
# filed stays in EDGAR under the same CIK. These are looked up by CIK instead.
CIK_OVERRIDES = {
    "SQ": 1512673,    # Block, Inc. -- ticker renamed to XYZ in 2025
    "ATVI": 718877,   # Activision Blizzard -- acquired by Microsoft, delisted
    "FL": 850209,     # Foot Locker -- acquired, delisted
}


def get_cik_for_ticker(ticker: str) -> int:
    """Look up a company's CIK number from SEC's official ticker mapping.

    Args:
        ticker: Stock ticker symbol, e.g. "NVDA".

    Returns:
        The company's CIK as an integer.

    Raises:
        ValueError: If the ticker is not found in SEC's mapping.
    """
    response = _get_with_retry(TICKER_MAP_URL, timeout=10)
    time.sleep(REQUEST_DELAY_SECONDS)

    for entry in response.json().values():
        if entry["ticker"].upper() == ticker.upper():
            return int(entry["cik_str"])

    # Checked only after SEC's own mapping, so a live ticker is never shadowed
    # by a stale hardcoded CIK.
    if ticker.upper() in CIK_OVERRIDES:
        return CIK_OVERRIDES[ticker.upper()]

    raise ValueError(f"Ticker {ticker!r} not found in SEC company_tickers.json")


DEFAULT_FORM_LIMITS = {"10-Q": 4, "10-K": 2}


def list_filings(
    ticker: str, cik: int, form_limits: dict[str, int] | None = None
) -> list[FilingMetadata]:
    """List a company's most recent filings, per form type.

    Depth matters: a 10-K filed in early 2019 reports fiscal year 2018, so
    answering questions about older periods requires reaching further back
    than the default two annual reports.

    Args:
        ticker: Stock ticker symbol, used to tag the returned metadata.
        cik: Company CIK number from get_cik_for_ticker().
        form_limits: {form_type: max_count}, e.g. {"10-K": 8, "8-K": 6}.
            Forms absent from this mapping are not collected.
            Defaults to DEFAULT_FORM_LIMITS.

    Returns:
        Filing metadata up to each form's limit, most recent first.
    """
    limits = dict(form_limits) if form_limits else dict(DEFAULT_FORM_LIMITS)

    url = SUBMISSIONS_URL.format(cik=cik)
    response = _get_with_retry(url, timeout=10)
    time.sleep(REQUEST_DELAY_SECONDS)

    recent = response.json()["filings"]["recent"]
    filings: list[FilingMetadata] = []
    counts = dict.fromkeys(limits, 0)

    for i, form in enumerate(recent["form"]):
        if form not in limits or counts[form] >= limits[form]:
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
    response = _get_with_retry(url, timeout=15)
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
    """Download and store all target filings for one company (S3 only).

    Standalone convenience wrapper for one-off/manual ingestion of a single
    company. scripts/bootstrap_corpus.py does NOT call this -- it inlines
    the same cik/list/download/store sequence itself because it needs the
    downloaded HTML content (to process/chunk/embed per filing, not just
    the S3 key) and per-filing fault isolation (continue past one bad
    filing instead of aborting the whole ticker), neither of which this
    function's narrower S3-keys-only contract supports.

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

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

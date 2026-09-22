"""TDD: filing depth must be configurable per company, and cover 8-K.

The corpus ingested only the last 2 10-Ks and 4 10-Qs, which in 2026 means
2025-2026 filings. FinanceBench asks about 2015-2024, so the corpus held the
right companies for the wrong years and nearly every question was
unanswerable -- the model correctly said the context did not contain it.
"""
from unittest.mock import MagicMock, patch

from pipeline.edgar_client import list_filings


def _submissions(forms_and_dates):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {
        "filings": {
            "recent": {
                "form": [f for f, _ in forms_and_dates],
                "filingDate": [d for _, d in forms_and_dates],
                "accessionNumber": [f"acc-{i}" for i in range(len(forms_and_dates))],
                "primaryDocument": [f"doc-{i}.htm" for i in range(len(forms_and_dates))],
            }
        }
    }
    return resp


# Ten years of annual filings, newest first, as EDGAR orders them
TEN_YEARS = [("10-K", f"{y}-02-05") for y in range(2026, 2016, -1)]


def test_deeper_history_is_returned_when_requested():
    """FY2018 data lives in a 10-K filed early 2019 -- reachable only with depth."""
    with patch("pipeline.edgar_client.requests.get", return_value=_submissions(TEN_YEARS)):
        filings = list_filings("MMM", 66740, form_limits={"10-K": 8})

    assert len(filings) == 8, f"expected 8 10-Ks, got {len(filings)}"
    assert filings[-1].filing_date == "2019-02-05", "did not reach back to the FY2018 filing"


def test_default_limits_stay_shallow():
    """Non-benchmark companies keep the cheap default depth."""
    with patch("pipeline.edgar_client.requests.get", return_value=_submissions(TEN_YEARS)):
        filings = list_filings("NVDA", 1045810)

    assert len(filings) == 2, f"default should return 2 10-Ks, got {len(filings)}"


def test_8k_is_ingestable():
    """9 FinanceBench questions ask about 8-K filings."""
    rows = [("8-K", "2026-01-05"), ("8-K", "2025-07-01"), ("10-K", "2026-02-05")]
    with patch("pipeline.edgar_client.requests.get", return_value=_submissions(rows)):
        filings = list_filings("PEP", 77476, form_limits={"8-K": 2, "10-K": 1})

    forms = [f.form_type for f in filings]
    assert forms.count("8-K") == 2, f"8-K not collected: {forms}"
    assert forms.count("10-K") == 1


def test_forms_outside_the_limits_are_ignored():
    """A form with no limit set must not be ingested."""
    rows = [("S-8", "2026-01-01"), ("4", "2026-01-02"), ("10-K", "2026-02-05")]
    with patch("pipeline.edgar_client.requests.get", return_value=_submissions(rows)):
        filings = list_filings("MMM", 66740, form_limits={"10-K": 5})

    assert [f.form_type for f in filings] == ["10-K"]


def test_benchmark_tickers_match_the_dataset():
    """BENCHMARK_TICKERS drives which companies get deep history. If it drifts
    from the dataset, those companies quietly revert to 2 annual reports and
    their questions become unanswerable again."""
    import json
    from pathlib import Path

    from scripts.bootstrap_corpus import BENCHMARK_TICKERS, TARGET_TICKERS

    fb_path = Path(__file__).parent.parent.parent / "evals/eval_data/financebench_150.json"
    if not fb_path.exists():
        return  # downloaded in CI before the eval job

    name_to_ticker = {
        "3M": "MMM", "Activision Blizzard": "ATVI", "Adobe": "ADBE",
        "AES Corporation": "AES", "Amazon": "AMZN", "Amcor": "AMCR",
        "AMD": "AMD", "American Express": "AXP", "American Water Works": "AWK",
        "Best Buy": "BBY", "Block": "SQ", "Boeing": "BA", "Coca-Cola": "KO",
        "Corning": "GLW", "Costco": "COST", "CVS Health": "CVS",
        "Foot Locker": "FL", "General Mills": "GIS",
        "Johnson & Johnson": "JNJ", "JPMorgan": "JPM", "Kraft Heinz": "KHC",
        "Lockheed Martin": "LMT", "MGM Resorts": "MGM", "Microsoft": "MSFT",
        "Netflix": "NFLX", "Nike": "NKE", "Paypal": "PYPL", "PepsiCo": "PEP",
        "Pfizer": "PFE", "Ulta Beauty": "ULTA", "Verizon": "VZ", "Walmart": "WMT",
    }
    rows = json.loads(fb_path.read_text())
    needed = {name_to_ticker.get(r["ticker"], r["ticker"]) for r in rows}

    assert not (needed - BENCHMARK_TICKERS), (
        f"benchmark companies without deep history: {sorted(needed - BENCHMARK_TICKERS)}"
    )
    assert not (BENCHMARK_TICKERS - set(TARGET_TICKERS)), (
        f"deep-history tickers not in the corpus: {sorted(BENCHMARK_TICKERS - set(TARGET_TICKERS))}"
    )

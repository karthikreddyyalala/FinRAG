"""TDD: delisted and renamed companies must still resolve to a CIK.

SEC's company_tickers.json lists only current registrants, so an acquired or
renamed company drops out of it -- while its historical 10-K/10-Q filings
remain in EDGAR under the same CIK. FinanceBench asks about several such
companies, so losing them loses real benchmark coverage.
"""
from unittest.mock import MagicMock, patch

import pytest

from pipeline.edgar_client import CIK_OVERRIDES, get_cik_for_ticker


def _ticker_map_without(*absent):
    """SEC response containing everything except the given tickers."""
    entries = {
        "0": {"ticker": "NVDA", "cik_str": 1045810, "title": "NVIDIA CORP"},
        "1": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple Inc."},
    }
    entries = {k: v for k, v in entries.items() if v["ticker"] not in absent}
    resp = MagicMock()
    resp.json.return_value = entries
    resp.raise_for_status.return_value = None
    return resp


@pytest.mark.parametrize("ticker", sorted(CIK_OVERRIDES))
def test_delisted_ticker_resolves_via_override(ticker):
    """Each override resolves without appearing in SEC's current-registrant map."""
    with patch("pipeline.edgar_client.requests.get", return_value=_ticker_map_without()):
        assert get_cik_for_ticker(ticker) == CIK_OVERRIDES[ticker]


def test_override_does_not_shadow_a_live_ticker():
    """A ticker present in SEC's map must still use SEC's own answer."""
    with patch("pipeline.edgar_client.requests.get", return_value=_ticker_map_without()):
        assert get_cik_for_ticker("NVDA") == 1045810


def test_genuinely_unknown_ticker_still_raises():
    with patch("pipeline.edgar_client.requests.get", return_value=_ticker_map_without()):
        with pytest.raises(ValueError, match="not found"):
            get_cik_for_ticker("NOTAREALTICKER")


def test_overrides_cover_the_known_delisted_financebench_companies():
    """Block renamed SQ->XYZ; Activision and Foot Locker were acquired."""
    for ticker in ("SQ", "ATVI", "FL"):
        assert ticker in CIK_OVERRIDES, f"{ticker} missing from CIK_OVERRIDES"

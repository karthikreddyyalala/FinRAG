"""TDD: EDGAR calls must survive transient network failures.

Three separate corpus builds were lost to DNS resolution failures partway
through -- the laptop's connection dropped, every subsequent ticker raised,
and the run rebuilt BM25 over only the companies it had managed to reach.
"""
from unittest.mock import MagicMock, patch

import pytest
import requests

from pipeline.edgar_client import _get_with_retry


def _ok(payload=None):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload or {}
    return resp


def test_transient_connection_error_is_retried_then_succeeds():
    attempts = []

    def flaky(url, **kwargs):
        attempts.append(url)
        if len(attempts) < 3:
            raise requests.exceptions.ConnectionError("temporary DNS failure")
        return _ok({"ok": True})

    with patch("pipeline.edgar_client.requests.get", side_effect=flaky):
        with patch("pipeline.edgar_client.time.sleep"):  # no real backoff in tests
            resp = _get_with_retry("https://data.sec.gov/x.json")

    assert resp.json() == {"ok": True}
    assert len(attempts) == 3, f"expected 3 attempts, got {len(attempts)}"


def test_persistent_network_failure_still_raises():
    def always_fails(url, **kwargs):
        raise requests.exceptions.ConnectionError("network is down")

    with patch("pipeline.edgar_client.requests.get", side_effect=always_fails):
        with patch("pipeline.edgar_client.time.sleep"):
            with pytest.raises(requests.exceptions.ConnectionError):
                _get_with_retry("https://data.sec.gov/x.json")


def _http_error(status: int):
    """A response whose raise_for_status raises with a real status attached."""
    resp = MagicMock()
    resp.status_code = status
    err = requests.exceptions.HTTPError(f"{status}")
    err.response = resp
    resp.raise_for_status.side_effect = err
    return resp


def test_404_is_not_retried():
    """A 404 is a real answer, not a transient fault -- retrying just wastes
    the SEC's rate limit."""
    attempts = []

    def not_found(url, **kwargs):
        attempts.append(url)
        return _http_error(404)

    with patch("pipeline.edgar_client.requests.get", side_effect=not_found):
        with patch("pipeline.edgar_client.time.sleep"):
            with pytest.raises(requests.exceptions.HTTPError):
                _get_with_retry("https://data.sec.gov/missing.json")

    assert len(attempts) == 1, f"404 retried {len(attempts)} times"


def test_429_is_retried():
    """SEC rate-limits at 10 req/s. A 429 literally means "retry later" --
    a corpus build makes hundreds of sequential requests and will hit it."""
    attempts = []

    def rate_limited(url, **kwargs):
        attempts.append(url)
        if len(attempts) < 3:
            return _http_error(429)
        return _ok({"ok": True})

    with patch("pipeline.edgar_client.requests.get", side_effect=rate_limited):
        with patch("pipeline.edgar_client.time.sleep"):
            resp = _get_with_retry("https://data.sec.gov/x.json")

    assert resp.json() == {"ok": True}
    assert len(attempts) == 3, f"429 not retried; attempts={len(attempts)}"


def test_5xx_is_retried():
    """A server error is transient, not an answer about the resource."""
    attempts = []

    def flaky_server(url, **kwargs):
        attempts.append(url)
        if len(attempts) < 2:
            return _http_error(503)
        return _ok({"ok": True})

    with patch("pipeline.edgar_client.requests.get", side_effect=flaky_server):
        with patch("pipeline.edgar_client.time.sleep"):
            resp = _get_with_retry("https://data.sec.gov/x.json")

    assert resp.json() == {"ok": True}
    assert len(attempts) == 2


def test_succeeds_first_try_without_sleeping():
    with patch("pipeline.edgar_client.requests.get", return_value=_ok({"a": 1})):
        with patch("pipeline.edgar_client.time.sleep") as slept:
            _get_with_retry("https://data.sec.gov/x.json")
    slept.assert_not_called()

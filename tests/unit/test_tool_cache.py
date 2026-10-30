import time
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

from server.observability.tool_cache import cache_key, get_cached, put_cached

TABLE = "finrag-query-cache"
PAYLOAD = {"passages": [{"id": "a1", "page": 40, "text": "(1,577)"}], "note": None}


@pytest.fixture
def dynamodb(monkeypatch):
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(key, "testing")
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        resource.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "query_hash", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "query_hash", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield resource


def test_round_trip_returns_the_same_payload_with_plain_numbers(dynamodb):
    put_cached(dynamodb, TABLE, "search_sec_filings", {"question": "3M capex"}, PAYLOAD)
    cached = get_cached(dynamodb, TABLE, "search_sec_filings", {"question": "3M capex"})
    assert cached == PAYLOAD
    assert type(cached["passages"][0]["page"]) is int  # not Decimal


def test_other_tools_and_arguments_miss(dynamodb):
    put_cached(dynamodb, TABLE, "search_sec_filings", {"question": "3M capex"}, PAYLOAD)
    assert get_cached(dynamodb, TABLE, "get_company_financials", {"question": "3M capex"}) is None
    assert get_cached(dynamodb, TABLE, "search_sec_filings", {"question": "AMD capex"}) is None


def test_key_ignores_case_and_spacing():
    assert cache_key("t", {"q": "3M  Capex"}) == cache_key("t", {"q": "3m capex"})


def test_expired_entry_is_a_miss(dynamodb, monkeypatch):
    put_cached(dynamodb, TABLE, "t", {"q": 1}, PAYLOAD)
    monkeypatch.setattr(time, "time", lambda: 10**10)
    assert get_cached(dynamodb, TABLE, "t", {"q": 1}) is None


def test_a_dynamodb_fault_is_a_miss_not_an_error():
    broken = MagicMock()
    broken.Table.side_effect = RuntimeError("down")
    assert get_cached(broken, TABLE, "t", {}) is None
    put_cached(broken, TABLE, "t", {}, PAYLOAD)  # must not raise


def test_a_code_change_invalidates_the_cache(monkeypatch):
    """A deploy kept serving pre-deploy results for 24 h (Netflix FY2023, 2026-10-30)."""
    from server.observability import tool_cache

    before = cache_key("t", {"q": "netflix revenue fy2023"})
    monkeypatch.setattr(tool_cache, "CODE_VERSION", "other-build")
    assert cache_key("t", {"q": "netflix revenue fy2023"}) != before


def test_code_version_is_a_hash_of_the_server_source():
    from server.observability.tool_cache import CODE_VERSION

    assert len(CODE_VERSION) == 12

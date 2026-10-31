from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

import server.rate_limit as rate_limit
from server.rate_limit import PER_MINUTE, RateLimited, check_rate_limit

NOW = 1_793_000_000.0  # fixed clock, mid-day UTC


@pytest.fixture
def dynamodb(monkeypatch):
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(key, "testing")
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        resource.create_table(
            TableName=rate_limit.TABLE,
            KeySchema=[{"AttributeName": "bucket", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "bucket", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield resource


def test_allows_the_per_minute_limit_then_says_when_it_resets(dynamodb):
    for _ in range(PER_MINUTE):
        check_rate_limit(dynamodb, now=NOW)
    with pytest.raises(RateLimited) as err:
        check_rate_limit(dynamodb, now=NOW)
    assert 1 <= err.value.retry_after <= 60


def test_next_minute_starts_a_fresh_count(dynamodb):
    for _ in range(PER_MINUTE):
        check_rate_limit(dynamodb, now=NOW)
    check_rate_limit(dynamodb, now=NOW + 60)


def test_daily_limit_holds_across_minutes(dynamodb, monkeypatch):
    monkeypatch.setattr(rate_limit, "PER_DAY", 3)
    for i in range(3):
        check_rate_limit(dynamodb, now=NOW + i * 60)
    with pytest.raises(RateLimited) as err:
        check_rate_limit(dynamodb, now=NOW + 300)
    assert err.value.retry_after > 60


def test_a_dynamodb_fault_lets_the_call_through():
    broken = MagicMock()
    broken.Table.return_value.update_item.side_effect = RuntimeError("table down")
    check_rate_limit(broken, now=NOW)  # must not raise


def test_voyage_budget_allows_spend_until_the_daily_cap(dynamodb):
    from server.rate_limit import VOYAGE_TOKENS_PER_DAY, spend_voyage_tokens

    assert spend_voyage_tokens(dynamodb, VOYAGE_TOKENS_PER_DAY - 10, now=NOW)
    assert not spend_voyage_tokens(dynamodb, 100, now=NOW)  # would cross the cap
    assert spend_voyage_tokens(dynamodb, 10, now=NOW)       # exactly fills it
    assert spend_voyage_tokens(dynamodb, 100, now=NOW + 86_400)  # next UTC day


def test_voyage_budget_fails_closed():
    """A cost cap that cannot be read must not spend: unlike the call limit, it fails closed."""
    from server.rate_limit import spend_voyage_tokens

    broken = MagicMock()
    broken.Table.return_value.update_item.side_effect = RuntimeError("dynamodb down")
    assert not spend_voyage_tokens(broken, 100, now=NOW)

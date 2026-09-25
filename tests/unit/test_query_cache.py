import time
from unittest.mock import MagicMock

from server.observability.query_cache import (
    cache_key,
    get_cached_answer,
    normalize_query,
    put_cached_answer,
)


def test_normalize_query_folds_case_and_whitespace():
    assert normalize_query("  Nvidia   Revenue?  ") == "nvidia revenue?"
    assert normalize_query("nvidia revenue?") == "nvidia revenue?"


def test_cache_key_is_stable_for_equivalent_queries():
    assert cache_key("Nvidia  revenue?") == cache_key("nvidia revenue?")


def test_cache_key_differs_for_different_queries():
    assert cache_key("Nvidia revenue?") != cache_key("Apple revenue?")


def test_get_cached_answer_returns_none_on_miss():
    dynamodb = MagicMock()
    table = MagicMock()
    dynamodb.Table.return_value = table
    table.get_item.return_value = {}  # no "Item" key, real DynamoDB miss shape

    result = get_cached_answer(dynamodb, "finrag-query-cache", "q")

    assert result is None


def test_get_cached_answer_returns_payload_on_hit():
    dynamodb = MagicMock()
    table = MagicMock()
    dynamodb.Table.return_value = table
    table.get_item.return_value = {
        "Item": {
            "query_hash": cache_key("q"),
            "answer": "cached answer [NVDA 10-Q Q1-2026]",
            "citations": [{"ticker": "NVDA"}],
            "ttl": int(time.time()) + 3600,
        }
    }

    result = get_cached_answer(dynamodb, "finrag-query-cache", "q")

    assert result == {"answer": "cached answer [NVDA 10-Q Q1-2026]", "citations": [{"ticker": "NVDA"}]}


def test_get_cached_answer_treats_expired_ttl_as_a_miss():
    """Belt-and-suspenders check independent of DynamoDB's own TTL sweep,
    which is best-effort and can lag real time by minutes."""
    dynamodb = MagicMock()
    table = MagicMock()
    dynamodb.Table.return_value = table
    table.get_item.return_value = {
        "Item": {
            "answer": "stale",
            "citations": [],
            "ttl": int(time.time()) - 10,  # already expired
        }
    }

    result = get_cached_answer(dynamodb, "finrag-query-cache", "q")

    assert result is None


def test_get_cached_answer_never_raises_on_dynamodb_failure():
    dynamodb = MagicMock()
    dynamodb.Table.side_effect = RuntimeError("table not found")

    result = get_cached_answer(dynamodb, "finrag-query-cache", "q")

    assert result is None


def test_put_cached_answer_writes_hash_key_and_ttl():
    dynamodb = MagicMock()
    table = MagicMock()
    dynamodb.Table.return_value = table

    put_cached_answer(dynamodb, "finrag-query-cache", "Nvidia revenue?", "ans", [{"ticker": "NVDA"}])

    dynamodb.Table.assert_called_once_with("finrag-query-cache")
    item = table.put_item.call_args.kwargs["Item"]
    assert item["query_hash"] == cache_key("Nvidia revenue?")
    assert item["answer"] == "ans"
    assert item["citations"] == [{"ticker": "NVDA"}]
    assert item["ttl"] > int(time.time())
    assert item["ttl"] <= int(time.time()) + 24 * 60 * 60 + 5  # 24h TTL, small slack for test runtime


def test_put_cached_answer_never_raises_on_dynamodb_failure():
    dynamodb = MagicMock()
    dynamodb.Table.side_effect = RuntimeError("throttled")

    put_cached_answer(dynamodb, "finrag-query-cache", "q", "ans", [])  # must not raise

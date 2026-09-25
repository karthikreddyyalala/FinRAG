from decimal import Decimal
from unittest.mock import MagicMock

from server.observability.logger import estimate_cost_usd, log_query


def test_estimate_cost_usd_scales_with_text_length():
    short_cost = estimate_cost_usd("sonnet", "a" * 100, "b" * 100)
    long_cost = estimate_cost_usd("sonnet", "a" * 1000, "b" * 1000)

    assert 0 < short_cost < long_cost


def test_estimate_cost_usd_unknown_model_returns_zero_not_raise():
    assert estimate_cost_usd("bogus-model", "hi", "there") == 0.0


def test_estimate_cost_usd_output_weighted_higher_than_input():
    """Every model in the pricing table charges more per output token than
    input -- catches an accidental swap of the two rates."""
    input_only = estimate_cost_usd("sonnet", "x" * 1000, "")
    output_only = estimate_cost_usd("sonnet", "", "x" * 1000)

    assert output_only > input_only


def test_log_query_writes_one_item_with_decimal_cost():
    dynamodb = MagicMock()
    table = MagicMock()
    dynamodb.Table.return_value = table

    log_query(
        dynamodb, "finrag-query-logs",
        query="3M capex FY2018", rewritten_query="3M capital expenditure FY2018",
        answer="$1,577M [MMM 10-K 2019-02-07]",
        citations=[{"ticker": "MMM"}, {"ticker": "MMM"}],
        cost_usd=0.0123456789, latency_ms_total=3200,
        latency_ms_per_stage={"rewrite": 200, "generate": 1800},
    )

    dynamodb.Table.assert_called_once_with("finrag-query-logs")
    item = table.put_item.call_args.kwargs["Item"]
    assert item["query"] == "3M capex FY2018"
    assert item["cited_tickers"] == ["MMM"]
    assert item["cost_usd"] == Decimal("0.012346")  # rounded, DynamoDB-safe type
    assert item["latency_ms_total"] == 3200
    assert item["latency_ms_per_stage"] == {"rewrite": 200, "generate": 1800}


def test_log_query_never_raises_on_dynamodb_failure():
    dynamodb = MagicMock()
    dynamodb.Table.side_effect = RuntimeError("table not found")

    log_query(
        dynamodb, "finrag-query-logs", query="q", rewritten_query="q",
        answer="a", citations=[], cost_usd=0.0, latency_ms_total=100,
        latency_ms_per_stage={},
    )  # must not raise

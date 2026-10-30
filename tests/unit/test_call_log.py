import json
from unittest.mock import MagicMock

from server.observability.call_log import log_call

RESULT = {"results": {
    "MMM": {"passages": [{"ticker": "MMM"}, {"ticker": "MMM"}]},
    "AMD": {"error": "not covered"},
}}


def test_writes_one_record_with_passage_count_and_tickers(capsys):
    dynamodb = MagicMock()
    log_call(dynamodb, "finrag-query-logs", tool="compare_companies",
             arguments={"tickers": ["MMM", "AMD"]}, latency_ms=812, result=RESULT)

    item = dynamodb.Table.return_value.put_item.call_args.kwargs["Item"]
    assert item["tool"] == "compare_companies"
    assert item["n_passages"] == 2
    assert item["tickers"] == ["MMM"]
    assert item["latency_ms"] == 812
    line = capsys.readouterr().out.strip()
    assert line.startswith("finrag_call ")
    assert json.loads(line.removeprefix("finrag_call "))["tool"] == "compare_companies"


def test_long_arguments_are_truncated():
    dynamodb = MagicMock()
    log_call(dynamodb, "t", tool="verify_figures", arguments={"answer": "x" * 5000},
             latency_ms=3, result=None)
    assert len(dynamodb.Table.return_value.put_item.call_args.kwargs["Item"]["arguments"]) <= 500


def test_a_logging_fault_never_raises():
    broken = MagicMock()
    broken.Table.side_effect = RuntimeError("down")
    log_call(broken, "t", tool="x", arguments={}, latency_ms=1, result=None, error="boom")


def test_no_dynamodb_still_prints_the_line(capsys):
    log_call(None, "t", tool="x", arguments={}, latency_ms=1, result=None)
    assert "finrag_call" in capsys.readouterr().out


def test_dynamodb_item_expires_in_90_days_but_cloudwatch_line_does_not(capsys):
    import time
    dynamodb = MagicMock()
    log_call(dynamodb, "t", tool="verify_figures", arguments={}, latency_ms=1, result=None)
    item = dynamodb.Table.return_value.put_item.call_args.kwargs["Item"]
    assert abs(item["expires_at"] - (time.time() + 90 * 24 * 3600)) < 60
    assert "expires_at" not in capsys.readouterr().out

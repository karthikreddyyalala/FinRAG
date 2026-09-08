from unittest.mock import MagicMock

from server.retrieval.query_rewriter import rewrite_query


def _fake_bedrock_client(rewritten_text: str) -> MagicMock:
    client = MagicMock()
    client.converse.return_value = {
        "output": {"message": {"content": [{"text": rewritten_text}]}}
    }
    return client


def test_rewrite_query_calls_haiku_and_returns_text():
    client = _fake_bedrock_client(
        "Nvidia Corporation NVDA data center segment revenue Q1 2024 Q1 2026 10-Q"
    )

    result = rewrite_query(client, "How did Nvidia data center revenue change?")

    assert result == "Nvidia Corporation NVDA data center segment revenue Q1 2024 Q1 2026 10-Q"
    call_kwargs = client.converse.call_args.kwargs
    assert call_kwargs["modelId"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert "How did Nvidia data center revenue change?" in str(call_kwargs["messages"])


def test_rewrite_query_strips_whitespace():
    client = _fake_bedrock_client("  NVDA revenue  \n")

    result = rewrite_query(client, "NVDA revenue")

    assert result == "NVDA revenue"

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

    # The LLM rewrite is preserved, then GAAP phrasing is appended -- filings
    # label this line "net sales", not "revenue".
    assert result.startswith(
        "Nvidia Corporation NVDA data center segment revenue Q1 2024 Q1 2026 10-Q"
    )
    assert "net sales" in result
    call_kwargs = client.converse.call_args.kwargs
    assert call_kwargs["modelId"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert "How did Nvidia data center revenue change?" in str(call_kwargs["messages"])


def test_rewrite_query_strips_whitespace():
    client = _fake_bedrock_client("  NVDA revenue  \n")

    result = rewrite_query(client, "NVDA revenue")

    assert result.startswith("NVDA revenue")
    assert not result.startswith(" "), "leading whitespace survived"
    assert not result.endswith(" "), "trailing whitespace survived"

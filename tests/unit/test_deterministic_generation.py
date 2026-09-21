"""TDD: extraction calls must run at temperature=0.

No temperature was set anywhere, so both the query rewriter and answer
generator ran at each API's default (1.0 for gpt-4o-mini). The same
FinanceBench question, run twice through the identical fixed pipeline,
produced a correct answer once and "the context does not provide this
figure" once -- a coin flip on whether the model equates a GAAP line item
with the analyst's term for it. Financial extraction is not creative
writing; nothing here should vary run to run.
"""
from unittest.mock import MagicMock

from server.generation.answer_generator import generate_answer
from server.retrieval.query_rewriter import _rewrite_openai, rewrite_query


def _bedrock_converse_response(text: str) -> dict:
    return {"output": {"message": {"content": [{"text": text}]}}}


def test_bedrock_rewrite_uses_zero_temperature():
    client = MagicMock()
    client.converse.return_value = _bedrock_converse_response("NVDA revenue")

    rewrite_query(client, "NVDA revenue")

    kwargs = client.converse.call_args.kwargs
    config = kwargs.get("inferenceConfig", {})
    assert config.get("temperature") == 0, f"inferenceConfig={config}"


def test_openai_rewrite_fallback_uses_zero_temperature(monkeypatch):
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            msg = MagicMock()
            msg.message.content = "NVDA revenue"
            return MagicMock(choices=[msg])

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = MagicMock(completions=FakeCompletions())

    import server.retrieval.query_rewriter as qr

    monkeypatch.setattr(qr, "OpenAI", FakeClient, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    import openai

    monkeypatch.setattr(openai, "OpenAI", FakeClient)

    _rewrite_openai("NVDA revenue")
    assert captured.get("temperature") == 0, f"captured={captured}"


CHUNK = {
    "text": "Revenue $1B",
    "ticker": "X",
    "filing_type": "10-K",
    "period": "FY24",
    "page_number": None,
}


def test_bedrock_generation_uses_zero_temperature():
    client = MagicMock()
    client.converse.return_value = _bedrock_converse_response("Revenue was $1B [X 10-K FY24]")

    generate_answer(client, "What was revenue?", [CHUNK])

    kwargs = client.converse.call_args.kwargs
    config = kwargs.get("inferenceConfig", {})
    assert config.get("temperature") == 0, f"inferenceConfig={config}"


def test_openai_generation_fallback_uses_zero_temperature(monkeypatch):
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            msg = MagicMock()
            msg.message.content = "Revenue was $1B [X 10-K FY24]"
            return MagicMock(choices=[msg])

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = MagicMock(completions=FakeCompletions())

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    import openai

    monkeypatch.setattr(openai, "OpenAI", FakeClient)

    bedrock = MagicMock()
    bedrock.converse.side_effect = Exception("ThrottlingException")

    generate_answer(bedrock, "What was revenue?", [CHUNK])
    assert captured.get("temperature") == 0, f"captured={captured}"

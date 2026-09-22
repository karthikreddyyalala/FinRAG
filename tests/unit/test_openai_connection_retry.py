"""TDD: the OpenAI fallback must retry transient connection errors too.

Bedrock correctly failed over to _call_openai() on a network timeout, but
_call_openai()'s own retry loop only recognized "429"/"rate_limit" in the
exception text -- a generic openai.APIConnectionError matched neither, so
it re-raised and killed a 150-question eval run at question 150 of 150.
"""
from unittest.mock import MagicMock

import httpx
import openai

from server.generation.answer_generator import generate_answer

CHUNK = {
    "text": "Revenue $1B",
    "ticker": "X",
    "filing_type": "10-K",
    "period": "FY24",
    "page_number": None,
}


def _connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/x"))


def test_connection_error_is_retried_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def create(**kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _connection_error()
        msg = MagicMock()
        msg.message.content = "Revenue was $1B [X 10-K FY24]"
        return MagicMock(choices=[msg])

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = MagicMock(completions=MagicMock(create=create))

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai, "OpenAI", FakeClient)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    bedrock = MagicMock()
    bedrock.converse.side_effect = Exception("ThrottlingException")

    result = generate_answer(bedrock, "What was revenue?", [CHUNK])
    assert "1B" in result
    assert calls["n"] == 3, f"expected 2 retries then success, got {calls['n']} attempts"


def test_persistent_connection_error_eventually_raises(monkeypatch):
    def create(**kwargs):
        raise _connection_error()

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = MagicMock(completions=MagicMock(create=create))

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai, "OpenAI", FakeClient)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    bedrock = MagicMock()
    bedrock.converse.side_effect = Exception("ThrottlingException")

    import pytest

    with pytest.raises(Exception):  # must not hang forever; must terminate
        generate_answer(bedrock, "What was revenue?", [CHUNK])

"""TDD: _rewrite_openai must retry transient connection errors.

It had no retry loop at all -- a single call. answer_generator.py's fallback
already needed this fix (a connection blip there killed a 150-question run
at the very last question); this function runs on every single question, so
it carries the same risk and previously had even less protection.
"""
from unittest.mock import MagicMock

import httpx
import openai
import pytest

from server.retrieval.query_rewriter import _rewrite_openai


def _connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/x"))


def test_connection_error_is_retried_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def create(**kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _connection_error()
        msg = MagicMock()
        msg.message.content = "NVDA revenue"
        return MagicMock(choices=[msg])

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = MagicMock(completions=MagicMock(create=create))

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai, "OpenAI", FakeClient)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    result = _rewrite_openai("NVDA revenue")
    assert result == "NVDA revenue"
    assert calls["n"] == 3


def test_persistent_connection_error_eventually_raises(monkeypatch):
    def create(**kwargs):
        raise _connection_error()

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = MagicMock(completions=MagicMock(create=create))

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai, "OpenAI", FakeClient)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    with pytest.raises(Exception):
        _rewrite_openai("NVDA revenue")

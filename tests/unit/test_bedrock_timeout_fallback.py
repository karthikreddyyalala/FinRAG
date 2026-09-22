"""TDD: a Bedrock network timeout must fall back to OpenAI, not crash.

A 150-question eval run died on ReadTimeoutError from bedrock-runtime with
99/150 already checkpointed -- costing nothing to resume, but only because
the checkpoint happened to save first. _is_bedrock_unavailable only matched
"Throttling" and "ResourceNotFoundException" in the exception text, so a
transient network timeout (a real botocore exception class, not a throttle)
propagated straight past the fallback and killed the process.
"""
from unittest.mock import MagicMock

import botocore.exceptions

from server.generation.answer_generator import _is_bedrock_unavailable
from server.retrieval.query_rewriter import _is_bedrock_unavailable as qr_unavailable


def _read_timeout() -> botocore.exceptions.ReadTimeoutError:
    return botocore.exceptions.ReadTimeoutError(endpoint_url="https://bedrock-runtime/x")


def _connect_timeout() -> botocore.exceptions.ConnectTimeoutError:
    return botocore.exceptions.ConnectTimeoutError(endpoint_url="https://bedrock-runtime/x")


def test_read_timeout_is_treated_as_unavailable():
    assert _is_bedrock_unavailable(_read_timeout())


def test_connect_timeout_is_treated_as_unavailable():
    assert _is_bedrock_unavailable(_connect_timeout())


def test_generic_socket_timeout_is_treated_as_unavailable():
    assert _is_bedrock_unavailable(TimeoutError("timed out"))


def test_query_rewriter_shares_the_same_widened_check():
    assert qr_unavailable(_read_timeout())


def test_unrelated_errors_still_propagate():
    """The fallback must not swallow real bugs -- only availability faults."""
    assert not _is_bedrock_unavailable(ValueError("chunks list is empty"))
    assert not _is_bedrock_unavailable(KeyError("ticker"))


def test_generate_answer_falls_back_on_read_timeout(monkeypatch):
    """End to end: a Bedrock timeout must reach the OpenAI path, not raise."""
    from server.generation.answer_generator import generate_answer

    bedrock = MagicMock()
    bedrock.converse.side_effect = _read_timeout()

    class FakeCompletions:
        def create(self, **kwargs):
            msg = MagicMock()
            msg.message.content = "Revenue was $1B [X 10-K FY24]"
            return MagicMock(choices=[msg])

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = MagicMock(completions=FakeCompletions())

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    import openai

    monkeypatch.setattr(openai, "OpenAI", FakeClient)

    chunk = {
        "text": "Revenue $1B",
        "ticker": "X",
        "filing_type": "10-K",
        "period": "FY24",
        "page_number": None,
    }
    result = generate_answer(bedrock, "What was revenue?", [chunk])
    assert "1B" in result

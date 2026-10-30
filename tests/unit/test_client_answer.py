from unittest.mock import MagicMock

import openai
import pytest

from evals.client_answer import DEFAULT_MODEL, eval_model, write_answer

PASSAGES = [{"text": "Purchases of PP&E (1,577)", "citation": "[MMM 10-K 2019-02-07 p.40]"}]


def _client(*responses):
    client = MagicMock()
    client.chat.completions.create.side_effect = list(responses)
    return client


def _ok(text):
    return MagicMock(choices=[MagicMock(message=MagicMock(content=text))])


def test_writes_from_passages_at_temperature_zero_with_a_token_cap():
    client = _client(_ok("3M spent $1,577 million [MMM 10-K 2019-02-07 p.40]."))
    answer = write_answer("3M capex FY2018?", PASSAGES, model="gpt-4o-mini", client=client)
    assert answer.startswith("3M spent")
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["temperature"] == 0 and kwargs["max_tokens"] == 1024
    assert "[MMM 10-K 2019-02-07 p.40]" in kwargs["messages"][1]["content"]


def test_model_defaults_and_can_be_overridden(monkeypatch):
    monkeypatch.delenv("FINRAG_EVAL_MODEL", raising=False)
    assert eval_model() == DEFAULT_MODEL
    monkeypatch.setenv("FINRAG_EVAL_MODEL", "gpt-4.1")
    assert eval_model() == "gpt-4.1"


def test_connection_errors_are_retried(monkeypatch):
    monkeypatch.setattr("evals.client_answer.time.sleep", lambda s: None)
    err = openai.APIConnectionError(request=MagicMock())
    client = _client(err, _ok("ok"))
    assert write_answer("q", PASSAGES, model="m", client=client) == "ok"


def test_no_credits_fails_at_once_instead_of_waiting():
    client = _client(RuntimeError("Error code: 429 - insufficient_quota"))
    with pytest.raises(RuntimeError, match="insufficient_quota"):
        write_answer("q", PASSAGES, model="m", client=client)
    assert client.chat.completions.create.call_count == 1

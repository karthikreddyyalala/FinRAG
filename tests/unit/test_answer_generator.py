from unittest.mock import MagicMock

from server.generation.answer_generator import format_citation, generate_answer


def _fake_bedrock_client(answer_text: str) -> MagicMock:
    client = MagicMock()
    client.converse.return_value = {
        "output": {"message": {"content": [{"text": answer_text}]}}
    }
    return client


def test_format_citation_matches_claude_md_format():
    chunk = {"ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026", "page_number": 23}

    citation = format_citation(chunk)

    assert citation == "[NVDA 10-Q Q1-2026 p.23]"


def test_format_citation_omits_page_when_none():
    chunk = {"ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026", "page_number": None}

    citation = format_citation(chunk)

    assert citation == "[NVDA 10-Q Q1-2026]"


def test_generate_answer_calls_sonnet_with_context_and_citations():
    client = _fake_bedrock_client("Data center revenue grew [NVDA 10-Q Q1-2026].")
    chunks = [
        {
            "chunk_id": "c1",
            "text": "Data center revenue reached $9.06 billion.",
            "ticker": "NVDA",
            "filing_type": "10-Q",
            "period": "Q1-2026",
            "page_number": None,
        }
    ]

    answer = generate_answer(client, "How did Nvidia data center revenue change?", chunks)

    assert answer == "Data center revenue grew [NVDA 10-Q Q1-2026]."
    call_kwargs = client.converse.call_args.kwargs
    assert call_kwargs["modelId"] == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert "$9.06 billion" in str(call_kwargs["messages"])
    assert "[NVDA 10-Q Q1-2026]" in str(call_kwargs["system"])


def test_generate_answer_handles_empty_chunks_list():
    client = _fake_bedrock_client("I could not find reliable data for this question.")

    answer = generate_answer(client, "What was Nvidia's revenue?", [])

    assert answer == "I could not find reliable data for this question."
    call_kwargs = client.converse.call_args.kwargs
    assert "[TICKER 10-Q PERIOD]" in str(call_kwargs["system"])  # fallback example citation used

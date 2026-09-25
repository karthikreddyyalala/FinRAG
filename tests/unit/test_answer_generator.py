from unittest.mock import MagicMock

from server.generation.answer_generator import MAX_CHUNK_CHARS, format_citation, generate_answer


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


def test_generate_answer_handles_empty_chunks_list():
    client = _fake_bedrock_client("I could not find reliable data for this question.")

    answer = generate_answer(client, "What was Nvidia's revenue?", [])

    assert answer == "I could not find reliable data for this question."


def test_system_prompt_is_identical_regardless_of_chunk_content():
    """Bedrock prompt caching (C3) only pays off if the system prompt is a
    byte-identical prefix across calls. It used to interpolate chunks[0]'s
    own citation as the worked example, so the "fixed" prompt actually
    varied per query -- a cache write that could never be reused. The
    worked example is now a constant, unrelated to the real chunks."""
    client_a = _fake_bedrock_client("ans")
    client_b = _fake_bedrock_client("ans")
    chunks_a = [
        {
            "chunk_id": "c1",
            "text": "Data center revenue reached $9.06 billion.",
            "ticker": "NVDA",
            "filing_type": "10-Q",
            "period": "Q1-2026",
            "page_number": None,
        }
    ]
    chunks_b = [
        {
            "chunk_id": "c2",
            "text": "Purchases of property, plant and equipment $(1,577)",
            "ticker": "MMM",
            "filing_type": "10-K",
            "period": "FY2018",
            "page_number": 40,
        }
    ]

    generate_answer(client_a, "query one", chunks_a)
    generate_answer(client_b, "query two", chunks_b)
    generate_answer(client_b, "query two", [])

    system_a = client_a.converse.call_args.kwargs["system"]
    system_b = client_b.converse.call_args.kwargs["system"]
    assert system_a == system_b


def test_generate_answer_truncates_an_oversized_chunk():
    """Live bug: a BM25-only match (no dense/rerank screening) surfaced a
    huge table chunk that blew Sonnet's context window outright -- caught on
    the FinanceBench 150 Baseline B run, question 91/150."""
    client = _fake_bedrock_client("Answer [NVDA 10-Q Q1-2026].")
    chunks = [
        {
            "chunk_id": "c1",
            "text": "x" * (MAX_CHUNK_CHARS + 5000),
            "ticker": "NVDA",
            "filing_type": "10-Q",
            "period": "Q1-2026",
            "page_number": None,
        }
    ]

    generate_answer(client, "q", chunks)

    sent_context = str(client.converse.call_args.kwargs["messages"])
    assert len(sent_context) < MAX_CHUNK_CHARS + 5000
    assert "[... truncated]" in sent_context

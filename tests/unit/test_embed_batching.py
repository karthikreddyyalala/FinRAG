"""TDD: embed_texts_openai must respect OpenAI's per-request limits.

A large 10-K (banks especially) produces enough chunks to exceed the
300k-token request cap. The API rejects the whole call with a 400, and
bootstrap_ticker's except-and-continue turns that into silently missing
filings -- the corpus looks fine and the company is simply absent.
"""
from unittest.mock import MagicMock, patch

from pipeline.sync_pinecone import (
    MAX_ITEMS_PER_REQUEST,
    MAX_TOKENS_PER_REQUEST,
    OBSERVED_SERVER_TOKEN_RATIO,
    embed_texts_openai,
)


def _fake_client(recorder):
    """Client that records each request's input and echoes back indexed vectors."""

    def create(input, model):  # noqa: A002 - mirrors the OpenAI kwarg name
        recorder.append(input)
        data = [MagicMock(index=i, embedding=[float(i)] * 4) for i in range(len(input))]
        return MagicMock(data=data)

    client = MagicMock()
    client.embeddings.create = create
    return client


def test_splits_when_token_budget_exceeded():
    """6000-char chunks are ~1500 tokens; enough of them must span requests."""
    texts = ["x" * 6000] * 400  # ~600k estimated tokens, over the 300k cap
    calls: list = []

    with patch("pipeline.sync_pinecone._get_openai_client", return_value=_fake_client(calls)):
        out = embed_texts_openai(texts)

    assert len(calls) > 1, "oversized batch was sent as a single request"
    assert len(out) == len(texts), f"expected {len(texts)} vectors, got {len(out)}"


def test_splits_when_item_count_exceeded():
    """OpenAI caps inputs per request regardless of token count."""
    texts = ["short"] * (MAX_ITEMS_PER_REQUEST + 50)
    calls: list = []

    with patch("pipeline.sync_pinecone._get_openai_client", return_value=_fake_client(calls)):
        out = embed_texts_openai(texts)

    assert all(len(c) <= MAX_ITEMS_PER_REQUEST for c in calls), "a request exceeded the item cap"
    assert len(out) == len(texts)


def test_no_request_exceeds_the_token_budget():
    """Counted with the real tokenizer, not a chars/4 guess.

    Dense financial tables tokenize at up to ~0.63 tokens/char -- 2.5x worse
    than chars/4 -- which is how a "250k" batch really carried 631k tokens
    and got rejected.
    """
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    # Digit-heavy content, the worst case for tokenization
    texts = ["1,234,567.89 9,876,543.21 " * 240] * 400
    calls: list = []

    with patch("pipeline.sync_pinecone._get_openai_client", return_value=_fake_client(calls)):
        embed_texts_openai(texts)

    for call in calls:
        local = sum(len(enc.encode(t)) for t in call)
        assert local <= MAX_TOKENS_PER_REQUEST, f"request carried {local} tokens"
        # OpenAI's own count runs ~1.24x the local one, and that is what the
        # 300k cap is enforced against.
        server_side = local * OBSERVED_SERVER_TOKEN_RATIO
        assert server_side <= 300_000, (
            f"{local} local tokens bills as ~{server_side:.0f} server-side, over the cap"
        )


def test_small_batch_still_sent_as_one_request():
    texts = ["short text"] * 10
    calls: list = []

    with patch("pipeline.sync_pinecone._get_openai_client", return_value=_fake_client(calls)):
        out = embed_texts_openai(texts)

    assert len(calls) == 1, "small batch was needlessly split"
    assert len(out) == 10


def test_vectors_return_in_input_order():
    """Order is load-bearing -- sync_chunks_to_pinecone zips vectors to chunks."""
    texts = [f"chunk {i}" for i in range(300)]
    calls: list = []

    with patch("pipeline.sync_pinecone._get_openai_client", return_value=_fake_client(calls)):
        out = embed_texts_openai(texts)

    assert len(out) == 300
    assert all(len(v) == 4 for v in out)

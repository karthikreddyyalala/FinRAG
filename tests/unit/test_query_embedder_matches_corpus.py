"""TDD: the production server must embed queries with the corpus's model.

The corpus in Pinecone is embedded with OpenAI text-embedding-3-small, but
server/main.py built its query embedder as partial(embed_text, bedrock) --
Titan. The eval harness wired the right embedder via get_embed_fn(), which is
why eval scores were real; the server itself would have queried Pinecone
with vectors from a different model and silently returned unrelated chunks.
"""
from unittest.mock import MagicMock, patch

from pipeline.sync_pinecone import embed_text_openai, get_embed_fn


def test_production_query_embedder_is_the_ingestion_model():
    import server.main as main

    with (
        patch.object(main, "boto3", MagicMock()),
        patch.object(main, "get_pinecone_index", MagicMock()),
        patch.object(main, "load_keyword_index", MagicMock()),
        patch.dict("os.environ", {"PINECONE_API_KEY": "k"}),
    ):
        deps = main._build_production_dependencies()

    embed_fn = deps[3]  # (bedrock, pinecone, keyword_index, embed_fn, dynamodb_resource)
    assert embed_fn is embed_text_openai, (
        f"server embeds queries with {embed_fn!r}; corpus was embedded with "
        "OpenAI text-embedding-3-small"
    )


def test_eval_and_server_share_one_embedder():
    """One source of truth: the harness and the server must not drift apart."""
    assert get_embed_fn() is embed_text_openai

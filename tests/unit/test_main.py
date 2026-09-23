from unittest.mock import MagicMock

from server.main import create_app


def test_create_app_returns_fastapi_app_with_mcp_mounted():
    bedrock_client = MagicMock()
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {"matches": []}
    keyword_index = MagicMock()
    embed_fn = MagicMock(return_value=[0.0])

    app = create_app(bedrock_client, pinecone_index, keyword_index, embed_fn)

    route_paths = [getattr(r, "path", None) for r in app.routes]
    assert any(path in ("/", "") for path in route_paths)

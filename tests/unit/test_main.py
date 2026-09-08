from unittest.mock import MagicMock

from server.main import create_app


def test_create_app_returns_fastapi_app_with_mcp_mounted():
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {"matches": []}
    embed_fn = MagicMock(return_value=[0.0])

    app = create_app(pinecone_index, embed_fn)

    # Starlette normalizes a root Mount's path to "" (verified against
    # starlette.routing.Mount directly: Mount("/", ...).path == "").
    route_paths = [getattr(r, "path", None) for r in app.routes]
    assert any(path in ("/", "") for path in route_paths)

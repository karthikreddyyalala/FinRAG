from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from server.main import create_app


def _app():
    bedrock_client = MagicMock()
    pinecone_index = MagicMock()
    pinecone_index.query.return_value = {"matches": []}
    keyword_index = MagicMock()
    keyword_index.search.return_value = []
    embed_fn = MagicMock(return_value=[0.0])
    return create_app(bedrock_client, pinecone_index, keyword_index, embed_fn, auth_token="t")


def test_create_app_returns_fastapi_app_with_mcp_mounted():
    app = _app()

    route_paths = [getattr(r, "path", None) for r in app.routes]
    assert any(path in ("/", "") for path in route_paths)


def test_middleware_accepts_a_valid_cognito_token_alongside_the_static_one():
    """Dual-accept, not a hard cutover: the static bearer token is already
    verified working end to end (screenshot-confirmed in Claude Desktop).
    Cognito login needs an interactive browser consent screen this
    environment cannot complete, so both must work until a human confirms
    the OAuth path from an actual client."""
    app = _app()

    with (
        patch.dict(
            "os.environ",
            {"COGNITO_USER_POOL_ID": "us-east-1_Test", "COGNITO_CLIENT_ID": "client-1",
             "AWS_REGION": "us-east-1"},
        ),
        patch("server.main.validate_token", return_value={"client_id": "client-1"}),
        patch("server.main._get_jwks_client", return_value=MagicMock()),
        TestClient(app) as client,
    ):
        resp = client.post(
            "/mcp",
            headers={
                "authorization": "Bearer some-cognito-jwt",
                "accept": "application/json, text/event-stream",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )

    assert resp.status_code == 200


def test_middleware_rejects_an_invalid_cognito_token():
    app = _app()
    client = TestClient(app)

    with (
        patch.dict(
            "os.environ",
            {"COGNITO_USER_POOL_ID": "us-east-1_Test", "COGNITO_CLIENT_ID": "client-1",
             "AWS_REGION": "us-east-1"},
        ),
        patch("server.main.validate_token", side_effect=Exception("bad token")),
        patch("server.main._get_jwks_client", return_value=MagicMock()),
    ):
        resp = client.post(
            "/mcp",
            headers={
                "authorization": "Bearer not-a-real-jwt",
                "accept": "application/json, text/event-stream",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )

    assert resp.status_code == 401

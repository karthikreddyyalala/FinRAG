import os
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
    return create_app(bedrock_client, pinecone_index, keyword_index, embed_fn)


def test_create_app_returns_fastapi_app_with_mcp_mounted():
    app = _app()

    route_paths = [getattr(r, "path", None) for r in app.routes]
    assert any(path in ("/", "") for path in route_paths)


def test_create_app_threads_dynamodb_resource_to_search_filings_tool():
    """Phase C (CLAUDE.md): create_app must pass dynamodb_resource through
    to register_search_filings_tool, or per-query logging never wires up in
    production even though get_dependencies() builds the resource."""
    dynamodb = MagicMock()

    with patch("server.main.register_search_filings_tool") as mock_register:
        create_app(MagicMock(), MagicMock(), MagicMock(), MagicMock(), dynamodb)

    assert mock_register.call_args.kwargs["dynamodb_resource"] is dynamodb


def test_middleware_accepts_a_valid_cognito_token():
    """Cognito is the only accepted credential -- verified end to end in
    Claude Desktop on 2026-09-24; the interim static token is retired."""
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


def test_oauth_protected_resource_metadata_is_public_and_points_at_cognito():
    """mcp-remote's OAuth discovery starts by fetching this well-known path
    with no token at all -- it must not be behind the auth middleware, or
    discovery can never bootstrap. Without this endpoint a client has no way
    to find Cognito on its own."""
    app = _app()

    with (
        patch.dict(
            "os.environ",
            {"COGNITO_USER_POOL_ID": "us-east-1_Test", "COGNITO_CLIENT_ID": "client-1",
             "AWS_REGION": "us-east-1"},
        ),
        TestClient(app) as client,
    ):
        resp = client.get("/.well-known/oauth-protected-resource")

    assert resp.status_code == 200
    body = resp.json()
    assert body["authorization_servers"] == ["https://cognito-idp.us-east-1.amazonaws.com/us-east-1_Test"]


def test_oauth_protected_resource_metadata_absent_without_cognito_configured():
    app = _app()

    with patch.dict("os.environ"):
        for key in ("COGNITO_USER_POOL_ID", "COGNITO_CLIENT_ID", "AWS_REGION"):
            os.environ.pop(key, None)
        with TestClient(app) as client:
            resp = client.get("/.well-known/oauth-protected-resource")

    assert resp.status_code == 404


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

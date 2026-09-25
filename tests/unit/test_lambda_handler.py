"""TDD: the MCP server must actually work behind a Lambda Function URL.

Probing the app through Mangum with real Function URL events showed it could
never have worked on Lambda:
  - the first request got 421 "Invalid Host header": MCP's DNS-rebinding
    guard only admits localhost Host headers, and a Lambda URL is not one;
  - the second request to a warm Lambda crashed with LifespanFailure,
    because the session manager's run() may only be called once per instance
    and Mangum runs the lifespan on every invocation.
And with no auth, a public URL would let anyone spend the OpenAI budget.

Auth is Cognito-only (the interim static MCP_AUTH_TOKEN was retired once
Cognito login was verified end to end -- CLAUDE.md Phase 11, item A3).
"""
import json
from unittest.mock import MagicMock, patch

import pytest

HOST = "abc123.lambda-url.us-east-1.on.aws"
COGNITO_ENV = {
    "COGNITO_USER_POOL_ID": "us-east-1_Test", "COGNITO_CLIENT_ID": "client-1",
    "AWS_REGION": "us-east-1",
}


def _event(body, auth="Bearer some-cognito-jwt"):
    headers = {
        "host": HOST,
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
    }
    if auth is not None:
        headers["authorization"] = auth
    return {
        "version": "2.0",
        "rawPath": "/mcp",
        "rawQueryString": "",
        "headers": headers,
        "requestContext": {
            "http": {"method": "POST", "path": "/mcp", "sourceIp": "1.2.3.4",
                     "protocol": "HTTP/1.1", "userAgent": "test"},
            "domainName": HOST,
            "stage": "$default",
        },
        "body": json.dumps(body),
        "isBase64Encoded": False,
    }


INITIALIZE = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "test", "version": "0"}},
}
TOOLS_LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}


@pytest.fixture
def handler():
    """The real Lambda handler, with production dependencies and a valid
    Cognito token faked out."""
    import server.main as main

    keyword_index = MagicMock()
    keyword_index.search.return_value = []
    deps = (MagicMock(), MagicMock(), keyword_index, MagicMock(return_value=[0.0]))
    main.get_dependencies.cache_clear()
    with patch.object(main, "_build_production_dependencies", return_value=deps), \
         patch.object(main, "load_secrets_from_ssm"), \
         patch.object(main, "validate_token", return_value={"client_id": "client-1"}), \
         patch.object(main, "_get_jwks_client", return_value=MagicMock()), \
         patch.dict("os.environ", COGNITO_ENV):
        yield main.handler
    main.get_dependencies.cache_clear()


def test_request_through_a_lambda_url_host_is_not_rejected(handler):
    resp = handler(_event(INITIALIZE), MagicMock())
    assert resp["statusCode"] == 200, f"{resp['statusCode']}: {resp['body'][:200]}"


def test_warm_lambda_serves_repeated_invocations(handler):
    """The second request to a warm instance used to crash the lifespan."""
    for i in range(3):
        resp = handler(_event(INITIALIZE), MagicMock())
        assert resp["statusCode"] == 200, f"invocation {i + 1}: {resp['body'][:200]}"


def test_tools_list_exposes_search_sec_filings(handler):
    resp = handler(_event(TOOLS_LIST), MagicMock())
    assert resp["statusCode"] == 200, resp["body"][:200]
    tools = [t["name"] for t in json.loads(resp["body"])["result"]["tools"]]
    assert "search_sec_filings" in tools


def test_missing_token_is_rejected(handler):
    assert handler(_event(TOOLS_LIST, auth=None), MagicMock())["statusCode"] == 401


def test_token_without_bearer_scheme_is_rejected(handler):
    assert handler(_event(TOOLS_LIST, auth="some-cognito-jwt"), MagicMock())["statusCode"] == 401


def test_unauthenticated_request_never_triggers_a_cold_start():
    """Loading dependencies downloads a ~900 MB index and connects to
    Pinecone. An anonymous scanner hitting the public URL must be turned away
    before any of that -- otherwise each probe costs a full cold start."""
    import server.main as main

    main.get_dependencies.cache_clear()
    with patch.object(main, "_build_production_dependencies") as build, \
         patch.object(main, "load_secrets_from_ssm"):
        for auth in (None, "Bearer wrong", "not-bearer-scheme"):
            resp = main.handler(_event(TOOLS_LIST, auth=auth), MagicMock())
            assert resp["statusCode"] == 401
        build.assert_not_called()
    main.get_dependencies.cache_clear()


def test_well_known_discovery_bypasses_auth_at_the_handler_level(handler):
    """Caught live: the FastAPI route's auth bypass never runs, because
    handler() itself rejects unauthenticated requests before create_app()
    is ever built (that's the whole point of checking auth before the
    cold-start work). The discovery endpoint needs its own bypass here,
    not just in the FastAPI middleware."""
    event = _event(None, auth=None)
    event["rawPath"] = "/.well-known/oauth-protected-resource"
    event.pop("body", None)

    with patch.dict("os.environ", {
        "COGNITO_USER_POOL_ID": "us-east-1_Test", "AWS_REGION": "us-east-1",
    }):
        resp = handler(event, MagicMock())

    assert resp["statusCode"] == 200, resp["body"][:200]
    body = json.loads(resp["body"])
    assert body["authorization_servers"] == ["https://cognito-idp.us-east-1.amazonaws.com/us-east-1_Test"]


def test_well_known_discovery_never_triggers_a_cold_start():
    import server.main as main

    main.get_dependencies.cache_clear()
    event = _event(None, auth=None)
    event["rawPath"] = "/.well-known/oauth-protected-resource"
    event.pop("body", None)

    with (
        patch.object(main, "_build_production_dependencies") as build,
        patch.object(main, "load_secrets_from_ssm"),
    ):
        resp = main.handler(event, MagicMock())
        assert resp["statusCode"] == 404  # Cognito not configured in this test's env
        build.assert_not_called()
    main.get_dependencies.cache_clear()


def test_handler_accepts_a_valid_cognito_token(handler):
    resp = handler(_event(TOOLS_LIST, auth="Bearer some-cognito-jwt"), MagicMock())
    assert resp["statusCode"] == 200, resp["body"][:200]


def test_handler_rejects_an_invalid_cognito_token_without_a_cold_start():
    import server.main as main

    main.get_dependencies.cache_clear()
    with (
        patch.object(main, "_build_production_dependencies") as build,
        patch.object(main, "load_secrets_from_ssm"),
        patch.dict("os.environ", COGNITO_ENV),
        patch.object(main, "validate_token", side_effect=Exception("bad token")),
        patch.object(main, "_get_jwks_client", return_value=MagicMock()),
    ):
        resp = main.handler(_event(TOOLS_LIST, auth="Bearer not-a-real-jwt"), MagicMock())
        assert resp["statusCode"] == 401
        build.assert_not_called()
    main.get_dependencies.cache_clear()

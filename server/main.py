"""FastAPI app entry point with MCP tool registration for FinRAG MCP.

Serves the MCP streamable-HTTP transport from AWS Lambda behind a Function
URL. Three constraints shape this module, each found by driving the app
through Mangum with real Function URL events before deploying:

- Stateless JSON responses: Lambda cannot hold a server-sent-events stream
  open or keep session state between invocations.
- A fresh app per invocation: the MCP session manager's run() may only be
  called once per instance, and Mangum runs the lifespan on every
  invocation -- a warm Lambda's second request crashed. The expensive pieces
  (secrets, keyword index, Pinecone client) are cached separately in
  get_dependencies(); rebuilding the app wrapper itself takes milliseconds.
- Bearer-token auth, fail closed: a public URL would otherwise let anyone
  spend the OpenAI budget. Cognito OAuth 2.1/PKCE is the only accepted
  credential (the interim static token was retired once Cognito login was
  verified end to end -- see CLAUDE.md Phase 11, item A3).
"""
from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

import boto3
import jwt
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mangum import Mangum
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from pipeline.sync_pinecone import get_embed_fn, get_pinecone_index, load_keyword_index
from server.auth.cognito_validator import validate_token
from server.mcp_tools.compare_companies import register_compare_companies_tool
from server.mcp_tools.get_financials import register_get_financials_tool
from server.mcp_tools.get_latest_filing import register_get_latest_filing_tool
from server.mcp_tools.search_filings import register_search_filings_tool
from server.ssm_secrets import SECRET_PARAMETERS as SECRET_PARAMETERS  # re-export
from server.ssm_secrets import load_secrets_from_ssm

COGNITO_REQUIRED_SCOPE = "finrag/invoke"
WELL_KNOWN_OAUTH_PATH = "/.well-known/oauth-protected-resource"

PROCESSED_BUCKET = "finrag-processed-filings"
KEYWORD_INDEX_KEY = "keyword/index.sqlite"
# /tmp is the only writable path on Lambda and persists across warm invocations.
KEYWORD_INDEX_LOCAL_PATH = "/tmp/finrag/keyword.sqlite"

ProductionDependencies = tuple[Any, Any, Any, Callable[[str], list[float]], Any]


def create_app(
    bedrock_client: Any,
    pinecone_index: Any,
    keyword_index: Any,
    embed_fn: Callable[[str], list[float]],
    dynamodb_resource: Any = None,
) -> FastAPI:
    """Build the FastAPI app with the MCP server mounted at /mcp.

    Args:
        bedrock_client: A boto3 bedrock-runtime client.
        pinecone_index: A Pinecone Index handle for the search tool.
        keyword_index: sync_pinecone.KeywordIndex over the full corpus.
        embed_fn: Callable(text) -> embedding vector for embedding queries.
        dynamodb_resource: A boto3 DynamoDB resource for per-query cost/
            latency logging (server/observability/logger.py). None skips
            logging.

    Returns:
        A FastAPI app ready to serve via Mangum on Lambda.
    """
    mcp = MCPServer("FinRAG")
    register_search_filings_tool(
        mcp, bedrock_client, pinecone_index, keyword_index, embed_fn,
        dynamodb_resource=dynamodb_resource,
    )
    register_get_financials_tool(mcp, bedrock_client, pinecone_index, keyword_index, embed_fn)
    register_compare_companies_tool(mcp, bedrock_client, pinecone_index, keyword_index, embed_fn)
    register_get_latest_filing_tool(mcp, bedrock_client, keyword_index)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan)

    # Public by definition (RFC 9728): an OAuth client has no token yet when
    # it fetches this to discover where to get one. Must stay reachable
    # without auth, or a client's OAuth discovery can never bootstrap. (The
    # Lambda handler has its own earlier copy of this bypass -- see
    # WELL_KNOWN_OAUTH_PATH in handler() -- since its own auth check runs
    # before create_app() is ever called.)
    @app.get(WELL_KNOWN_OAUTH_PATH)
    async def oauth_protected_resource(request: Request) -> Any:
        metadata = _oauth_protected_resource_metadata(str(request.base_url))
        if metadata is None:
            return JSONResponse({"error": "not_found"}, status_code=404)
        return metadata

    # Also enforced in the app, not only the Lambda handler, so the app is
    # never open when served any other way (e.g. uvicorn locally).
    @app.middleware("http")
    async def require_bearer_token(request: Request, call_next: Any) -> Any:
        if request.url.path == WELL_KNOWN_OAUTH_PATH:
            return await call_next(request)
        if not _is_authorized(request.headers.get("authorization")):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

    app.mount(
        "/",
        mcp.streamable_http_app(
            json_response=True,
            stateless_http=True,
            # DNS-rebinding protection guards servers bound to localhost from
            # being reached by a malicious web page. This is a public HTTPS
            # endpoint behind bearer auth; the guard's localhost-only Host
            # allowlist just rejects every request (421) with a Lambda URL host.
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=False
            ),
        ),
    )
    return app


def _oauth_protected_resource_metadata(base_url: str) -> dict[str, Any] | None:
    """RFC 9728 protected-resource metadata, or None if Cognito isn't configured.

    Shared by the FastAPI route (local/uvicorn serving) and handler()'s own
    early bypass (Lambda, where auth is checked before create_app() runs).
    """
    pool_id = os.environ.get("COGNITO_USER_POOL_ID")
    region = os.environ.get("AWS_REGION")
    if not (pool_id and region):
        return None
    issuer = f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"
    return {"resource": f"{base_url.rstrip('/')}/mcp", "authorization_servers": [issuer]}


def _build_production_dependencies() -> ProductionDependencies:
    """Wire up real Bedrock, Pinecone, and keyword-index clients.

    Expects secrets already in the environment (the handler loads them).
    """
    bedrock_client = boto3.client("bedrock-runtime")
    s3_client = boto3.client("s3")
    pinecone_index = get_pinecone_index(
        api_key=os.environ["PINECONE_API_KEY"], index_name="finrag-filings"
    )
    keyword_index = load_keyword_index(
        s3_client, PROCESSED_BUCKET, KEYWORD_INDEX_KEY, KEYWORD_INDEX_LOCAL_PATH
    )
    # Must be the model the corpus was embedded with (OpenAI), not Titan --
    # querying Pinecone with another model's vectors returns unrelated chunks
    # without any error. get_embed_fn() is shared with the eval harness.
    embed_fn = get_embed_fn()
    dynamodb_resource = boto3.resource("dynamodb")
    return bedrock_client, pinecone_index, keyword_index, embed_fn, dynamodb_resource


@lru_cache(maxsize=1)
def get_dependencies() -> ProductionDependencies:
    """Build the expensive dependencies once per Lambda instance.

    Deferred past import time: loading secrets, the keyword index, and the
    Pinecone client all need live credentials and network access.
    """
    return _build_production_dependencies()


@lru_cache(maxsize=1)
def _get_jwks_client(pool_id: str, region: str) -> jwt.PyJWKClient:
    """Cached per Lambda instance -- reuses PyJWKClient's own key cache
    across warm invocations instead of refetching the JWKS on every request.
    """
    jwks_uri = f"https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/jwks.json"
    return jwt.PyJWKClient(jwks_uri)


def _is_authorized(authorization_header: str | None) -> bool:
    """Accept only a valid Cognito access token.

    The static bearer token was the interim path before Cognito login was
    confirmed end to end from a real client (Claude Desktop, 2026-09-24);
    it is retired -- see CLAUDE.md Phase 11, item A3.
    """
    header = authorization_header or ""
    if not header.startswith("Bearer "):
        return False
    supplied = header.removeprefix("Bearer ").strip()
    pool_id = os.environ.get("COGNITO_USER_POOL_ID")
    client_id = os.environ.get("COGNITO_CLIENT_ID")
    region = os.environ.get("AWS_REGION")
    if not (supplied and pool_id and client_id and region):
        return False

    issuer = f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"
    try:
        validate_token(
            supplied, _get_jwks_client(pool_id, region), issuer, client_id,
            required_scope=COGNITO_REQUIRED_SCOPE,
        )
        return True
    except Exception:
        # Fail closed on anything: bad signature, expired, wrong scope, or a
        # transient JWKS fetch failure should all read as unauthorized, not
        # crash the request.
        return False


def handler(event: Any, context: Any) -> Any:
    """Lambda entry point: auth first, then cached dependencies, fresh app.

    Auth is checked before get_dependencies(), which downloads a ~900 MB index
    and connects to Pinecone -- an anonymous scanner hitting the public URL
    must be turned away before that, or every probe costs a cold start.
    load_secrets_from_ssm is a no-op once the variables are set, so warm
    invocations make no SSM call.
    """
    load_secrets_from_ssm(
        boto3.client("ssm"), prefix=os.environ.get("FINRAG_SSM_PREFIX", "/finrag")
    )
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    if event.get("rawPath") == WELL_KNOWN_OAUTH_PATH:
        base_url = f"https://{headers.get('host', '')}/"
        metadata = _oauth_protected_resource_metadata(base_url)
        status = 200 if metadata is not None else 404
        body = metadata if metadata is not None else {"error": "not_found"}
        return {
            "statusCode": status,
            "headers": {"content-type": "application/json"},
            "body": json.dumps(body),
        }

    if not _is_authorized(headers.get("authorization")):
        return {
            "statusCode": 401,
            "headers": {"content-type": "application/json"},
            "body": '{"error": "unauthorized"}',
        }

    app = create_app(*get_dependencies())
    return Mangum(app, lifespan="auto")(event, context)

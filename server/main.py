"""FastAPI app entry point with MCP tool registration for FinRAG MCP.

Week 1 scope: one tool (search_sec_filings), direct Pinecone query, no
query rewriting, hybrid search, reranking, or generation model yet.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from functools import lru_cache, partial
from typing import Any

import boto3
from fastapi import FastAPI
from mangum import Mangum
from mcp.server import MCPServer

from pipeline.sync_pinecone import embed_text, get_pinecone_index
from server.mcp_tools.search_filings import register_search_filings_tool


def create_app(
    pinecone_index: Any, embed_fn: Callable[[str], list[float]]
) -> FastAPI:
    """Build the FastAPI app with the MCP server mounted.

    Args:
        pinecone_index: A Pinecone Index handle for the search tool.
        embed_fn: Callable(text) -> embedding vector for embedding queries.

    Returns:
        A FastAPI app ready to serve via Mangum on Lambda.
    """
    mcp = MCPServer("FinRAG")
    register_search_filings_tool(mcp, pinecone_index, embed_fn)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.mount("/", mcp.streamable_http_app())
    return app


def _build_production_dependencies() -> tuple[Any, Callable[[str], list[float]]]:
    """Wire up real Bedrock + Pinecone clients for production use."""
    bedrock_client = boto3.client("bedrock-runtime")
    pinecone_index = get_pinecone_index(
        api_key=os.environ["PINECONE_API_KEY"], index_name="finrag-filings"
    )
    return pinecone_index, partial(embed_text, bedrock_client)


@lru_cache(maxsize=1)
def get_app() -> FastAPI:
    """Build the production FastAPI app once, on first real use.

    Deferred past import time (rather than a module-level `app = ...`)
    because Pinecone's client resolves an index's host via a control-plane
    API call as soon as `pc.Index(name)` is constructed -- doing that
    eagerly at import would require live Pinecone credentials just to
    import this module, which breaks unit testing and needlessly slows
    every cold start that doesn't end up handling a request.
    """
    pinecone_index, embed_fn = _build_production_dependencies()
    return create_app(pinecone_index, embed_fn)


def handler(event: Any, context: Any) -> Any:
    """Lambda entry point. Builds the app lazily via `get_app()`."""
    return Mangum(get_app())(event, context)

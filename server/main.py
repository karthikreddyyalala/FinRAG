"""FastAPI app entry point with MCP tool registration for FinRAG MCP.

Week 2 scope: full four-stage pipeline (rewrite -> hybrid -> rerank ->
generate -> verify). BM25 index is loaded once from S3 at app startup
(inside get_app(), same lazy-construction pattern as the Pinecone index --
both need real credentials/network access, so neither happens at import time).
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

from pipeline.sync_pinecone import embed_text, get_pinecone_index, load_bm25_index
from server.mcp_tools.search_filings import register_search_filings_tool

PROCESSED_BUCKET = "finrag-processed-filings"
BM25_INDEX_KEY = "bm25/index.pkl"

ProductionDependencies = tuple[Any, Any, Any, list[dict[str, Any]], Callable[[str], list[float]]]


def create_app(
    bedrock_client: Any,
    pinecone_index: Any,
    bm25_index: Any,
    bm25_chunks: list[dict[str, Any]],
    embed_fn: Callable[[str], list[float]],
) -> FastAPI:
    """Build the FastAPI app with the MCP server mounted.

    Args:
        bedrock_client: A boto3 bedrock-runtime client.
        pinecone_index: A Pinecone Index handle for the search tool.
        bm25_index: The corpus-wide BM25 index.
        bm25_chunks: The chunks bm25_index was built from.
        embed_fn: Callable(text) -> embedding vector for embedding queries.

    Returns:
        A FastAPI app ready to serve via Mangum on Lambda.
    """
    mcp = MCPServer("FinRAG")
    register_search_filings_tool(
        mcp, bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.mount("/", mcp.streamable_http_app())
    return app


def _build_production_dependencies() -> ProductionDependencies:
    """Wire up real Bedrock + Pinecone + BM25 clients for production use."""
    bedrock_client = boto3.client("bedrock-runtime")
    s3_client = boto3.client("s3")
    pinecone_index = get_pinecone_index(
        api_key=os.environ["PINECONE_API_KEY"], index_name="finrag-filings"
    )
    bm25_index, bm25_chunks = load_bm25_index(s3_client, PROCESSED_BUCKET, BM25_INDEX_KEY)
    embed_fn = partial(embed_text, bedrock_client)
    return bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn


@lru_cache(maxsize=1)
def get_app() -> FastAPI:
    """Build the production FastAPI app once, on first real use.

    Deferred past import time -- Pinecone's client resolves an index's host
    via a control-plane API call at construction, and loading the BM25
    index requires a real S3 read, both of which would require live
    credentials just to import this module otherwise.
    """
    bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn = (
        _build_production_dependencies()
    )
    return create_app(bedrock_client, pinecone_index, bm25_index, bm25_chunks, embed_fn)


def handler(event: Any, context: Any) -> Any:
    """Lambda entry point. Builds the app lazily via `get_app()`."""
    return Mangum(get_app())(event, context)

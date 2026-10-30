"""Test helpers: a fake keyword index, and the real MCP SDK driven over HTTP."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

HEADERS = {"accept": "application/json, text/event-stream"}


def chunk(chunk_id, text, ticker="MMM", filing_type="10-K", period="2019-02-07", page=40):
    return {"chunk_id": chunk_id, "text": text, "ticker": ticker,
            "filing_type": filing_type, "period": period, "page_number": page}


class FakeKeywordIndex:
    """Same interface as pipeline.sync_pinecone.KeywordIndex, in memory."""

    def __init__(self, chunks: list[dict[str, Any]], bm25_ids: list[str] | None = None):
        self.chunks = {c["chunk_id"]: c for c in chunks}
        self.bm25_ids = list(self.chunks) if bm25_ids is None else bm25_ids
        self.queries: list[dict[str, Any]] = []

    def search(self, query, top_k=10, ticker=None, period_range=None):
        self.queries.append({"query": query, "ticker": ticker, "period_range": period_range})
        out = [self.chunks[i] for i in self.bm25_ids]
        if ticker:
            out = [c for c in out if c["ticker"] == ticker]
        if period_range:
            out = [c for c in out if period_range[0] <= c["period"] <= period_range[1]]
        return out[:top_k]

    def get_by_ids(self, ids):
        return {i: self.chunks[i] for i in ids if i in self.chunks}

    def coverage(self):
        rows: dict[tuple, int] = {}
        for c in self.chunks.values():
            key = (c["ticker"], c["filing_type"], c["period"])
            rows[key] = rows.get(key, 0) + 1
        return [
            {"ticker": t, "filing_type": f, "filed": p, "chunks": n}
            for (t, f, p), n in sorted(rows.items())
        ]


def pinecone_returning(matches: list[dict[str, Any]]):
    """A Pinecone index fake whose query() returns these matches."""
    from unittest.mock import MagicMock

    index = MagicMock()
    index.query.return_value = {"matches": matches}
    return index


@contextmanager
def tool_client(*registers, deps):
    """Yield call(name, arguments) -> (is_error, payload) over the real SDK.

    One TestClient for the whole block: the session manager's run() may only
    be entered once per MCPServer instance.
    """
    mcp = MCPServer("test")
    for register in registers:
        register(mcp, lambda: deps)

    @asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.mount("/", mcp.streamable_http_app(
        json_response=True, stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    ))
    with TestClient(app) as client:
        def call(name: str, arguments: dict[str, Any]):
            resp = client.post("/mcp", headers=HEADERS, json={
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            })
            body = resp.json()
            assert "result" in body, body
            result = body["result"]
            text = result["content"][0]["text"]
            return result["isError"], (text if result["isError"] else json.loads(text))

        yield call

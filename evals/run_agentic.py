# ruff: noqa: E501
"""End-to-end eval the way a user meets FinRAG: a model calling the real MCP tools in a loop.

The one-shot eval (run_remeasure.py) hands a model 5 passages from one search.
A real client (Claude, Cursor) reads the server instructions, picks tools,
searches again, and computes. This drives the real MCP server in-process (same
tool schemas, descriptions, validation and errors as production, live
Pinecone, Voyage and SEC), with gpt-4o-mini standing in for the client.

Scored three ways per question: right, wrong, refused. A wrong figure is worse
than a refusal, so neither count stands alone.

Run: PYTHONPATH=. python evals/run_agentic.py --tools search|full [--limit N] [--workers 4]
Needs OPENAI_API_KEY, PINECONE_API_KEY, VOYAGE_API_KEY. Resumable (per-question checkpoints).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from evals.analyze_baseline_gap import is_refusal, states_correct_number
from evals.run_eval import (
    CUSTOM,
    FINANCEBENCH,
    KEYWORD_INDEX_LOCAL_PATH,
    RESULTS_DIR,
    _load,
    verified_custom_items,
)

TOOLSETS = {
    "search": ("search_sec_filings", "list_covered_companies"),
    "full": ("search_sec_filings", "list_covered_companies", "get_company_financials",
             "compare_companies"),
}
MAX_ROUNDS = 8
MAX_TOOL_CHARS = 16_000
PRICE_IN, PRICE_OUT = 0.15 / 1e6, 0.60 / 1e6
CLIENT_PROMPT = """You are answering a question for a user with the FinRAG tools.
Use the tools to find the facts, then give a short final answer with the figure(s) and
their citations. If the question asks for a calculation, show the inputs and the result.
If the tools do not give you what you need, say what is missing."""


class McpClient:
    """The production MCP server, driven over its real HTTP transport in-process."""

    def __init__(self, deps):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from mcp.server import MCPServer
        from mcp.server.transport_security import TransportSecuritySettings

        from server.main import INSTRUCTIONS, REGISTERS

        self.instructions = INSTRUCTIONS
        mcp = MCPServer("FinRAG", instructions=INSTRUCTIONS)
        for register in REGISTERS:
            register(mcp, lambda: deps)

        @asynccontextmanager
        async def lifespan(app):
            async with mcp.session_manager.run():
                yield

        app = FastAPI(lifespan=lifespan)
        app.mount("/", mcp.streamable_http_app(
            json_response=True, stateless_http=True,
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)))
        self._client = TestClient(app)
        self._client.__enter__()
        self._lock = threading.Lock()

    def _rpc(self, method: str, params: dict) -> dict:
        with self._lock:
            resp = self._client.post("/mcp", headers={"accept": "application/json, text/event-stream"},
                                     json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        return resp.json()["result"]

    def tools(self, names: tuple[str, ...]) -> list[dict]:
        """OpenAI function specs built from the server's own tools/list."""
        return [{"type": "function", "function": {
                    "name": t["name"], "description": t.get("description", ""),
                    "parameters": t["inputSchema"]}}
                for t in self._rpc("tools/list", {})["tools"] if t["name"] in names]

    def call(self, name: str, arguments: dict) -> str:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        return result["content"][0]["text"] if result.get("content") else ""


def run_one(question: str, mcp: McpClient, tools: list[dict], oai, model: str) -> dict:
    messages = [{"role": "system", "content": f"{CLIENT_PROMPT}\n\nServer instructions:\n{mcp.instructions}"},
                {"role": "user", "content": question}]
    calls, contexts, usage = [], [], {"in": 0, "out": 0}
    for _ in range(MAX_ROUNDS):
        for attempt in range(6):
            try:
                resp = oai.chat.completions.create(model=model, messages=messages, tools=tools,
                                                   temperature=0, max_tokens=1200)
                break
            except Exception as e:  # rate limits and blips; insufficient_quota is fatal
                if "context_length_exceeded" in str(e):
                    # Searching round after round without settling; a real client
                    # would hit the same wall. Scored as no answer.
                    return {"answer": "", "calls": calls, "contexts": contexts, "usage": usage,
                            "note": "context window exceeded before a final answer"}
                if "insufficient_quota" in str(e) or attempt == 5:
                    raise
                time.sleep(2 ** attempt)
        usage["in"] += resp.usage.prompt_tokens
        usage["out"] += resp.usage.completion_tokens
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return {"answer": msg.content or "", "calls": calls, "contexts": contexts, "usage": usage}
        messages.append({"role": "assistant", "content": msg.content,
                         "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            text = mcp.call(tc.function.name, args)
            calls.append({"tool": tc.function.name, "arguments": args})
            contexts.append(text[:MAX_TOOL_CHARS])
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": text[:MAX_TOOL_CHARS]})
    return {"answer": "", "calls": calls, "contexts": contexts, "usage": usage,
            "note": f"no final answer after {MAX_ROUNDS} rounds"}


def score(rows: list[dict]) -> dict:
    """Right / wrong / refused over questions with a numeric ground truth."""
    right = wrong = refused = 0
    for r in rows:
        verdict = states_correct_number(r["answer"], r["ground_truth"])
        if verdict is None:
            continue
        if not r["answer"].strip() or is_refusal(r["answer"]):
            refused += 1
        elif verdict:
            right += 1
        else:
            wrong += 1
    answered = right + wrong
    return {"n": len(rows), "scorable": right + wrong + refused, "right": right, "wrong": wrong,
            "refused": refused, "right_when_answering": round(right / answered, 3) if answered else None,
            "refused_all": sum(not r["answer"].strip() or is_refusal(r["answer"]) for r in rows)}


def main() -> None:
    from openai import OpenAI
    from pinecone import Pinecone

    from evals.client_answer import eval_model
    from pipeline.sync_pinecone import get_embed_fn, load_keyword_index
    from server.mcp_tools.common import Deps

    toolset = sys.argv[sys.argv.index("--tools") + 1]
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 4
    model = eval_model()
    deps = Deps(Pinecone(api_key=os.environ["PINECONE_API_KEY"]).Index("finrag-filings"),
                load_keyword_index(None, "", "", KEYWORD_INDEX_LOCAL_PATH), get_embed_fn(), None)
    mcp = McpClient(deps)
    tools = mcp.tools(TOOLSETS[toolset])
    oai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    summary = {"date": time.strftime("%Y-%m-%d"), "model": model, "tools": [t["function"]["name"] for t in tools]}
    total = {"in": 0, "out": 0}
    for label, items in (("financebench", _load(FINANCEBENCH)), ("custom", verified_custom_items(_load(CUSTOM)))):
        items = items[:limit]
        path = RESULTS_DIR / f"agentic_{label}_{toolset}{'_limit' if limit else ''}.json"
        done = {r["question"]: r for r in json.loads(path.read_text())} if path.exists() else {}
        lock = threading.Lock()

        def work(item):
            q = item["question"]
            if q in done:
                return
            row = {"question": q, "ground_truth": item.get("ground_truth", ""), "model": model,
                   **run_one(q, mcp, tools, oai, model)}
            with lock:
                done[q] = row
                path.write_text(json.dumps([done[i["question"]] for i in items if i["question"] in done], indent=1))
                print(f"  [{label} {len(done)}/{len(items)}] {len(row['calls'])} calls  {q[:60]}", flush=True)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(work, items))
        rows = [done[i["question"]] for i in items]
        for r in rows:
            total["in"] += r["usage"]["in"]
            total["out"] += r["usage"]["out"]
        summary[label] = score(rows)
        summary[label]["avg_tool_calls"] = round(sum(len(r["calls"]) for r in rows) / len(rows), 2)
    summary["cost_usd_estimate"] = round(total["in"] * PRICE_IN + total["out"] * PRICE_OUT, 3)
    out = RESULTS_DIR / f"agentic_{toolset}{'_limit' if limit else ''}.json"
    out.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

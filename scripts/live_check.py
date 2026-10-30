"""Exercise the deployed FinRAG MCP server exactly as a client would, with no token.

Writes dashboard/data/live/live-check.json (latencies, a sample result per tool)
for the site. Paces calls under the server's 30/minute shared limit.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/live_check.py https://<function-url>/mcp
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import requests

OUT = Path("dashboard/data/live/live-check.json")
CAPEX_FACT = "xbrl:MMM:us-gaap:PaymentsToAcquirePropertyPlantAndEquipment:FY2018"
HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
PACE_SECONDS = 2.5
QUESTIONS = [
    "3M capital expenditure FY2018",
    "Nvidia data center revenue fiscal 2025",
    "Apple total net sales fiscal 2023",
    "Coca-Cola operating income 2022",
    "Tesla automotive revenue 2024",
    "JPMorgan net interest income 2023",
    "Walmart total revenues fiscal 2024",
    "Boeing net loss 2020",
    "Netflix revenue 2023",
    "Microsoft operating income fiscal 2024",
]


def rpc(url: str, method: str, params: dict, call_id: int = 1) -> tuple[dict, int]:
    start = time.monotonic()
    resp = requests.post(url, headers=HEADERS, timeout=130, json={
        "jsonrpc": "2.0", "id": call_id, "method": method, "params": params})
    ms = int((time.monotonic() - start) * 1000)
    resp.raise_for_status()
    return resp.json(), ms


def tool(url: str, name: str, arguments: dict) -> tuple[bool, object, int]:
    body, ms = rpc(url, "tools/call", {"name": name, "arguments": arguments})
    time.sleep(PACE_SECONDS)
    result = body["result"]
    text = result["content"][0]["text"]
    return result["isError"], (text if result["isError"] else json.loads(text)), ms


def trimmed(value):
    """Passage text cut to 600 chars so the site's data file stays small."""
    if isinstance(value, dict):
        return {k: (v[:600] if k == "text" and isinstance(v, str) else trimmed(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [trimmed(v) for v in value]
    return value


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    url = sys.argv[1]
    report: dict = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "url": url}

    init, report["initialize_ms"] = rpc(url, "initialize", {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "live-check", "version": "1"}})
    assert "verify_figures" in init["result"]["instructions"]
    listed, report["tools_list_ms"] = rpc(url, "tools/list", {})
    report["tools"] = sorted(t["name"] for t in listed["result"]["tools"])
    assert len(report["tools"]) == 6, report["tools"]

    samples = {}
    is_error, search, _ = tool(url, "search_sec_filings",
                               {"question": "3M capital expenditure", "ticker": "MMM",
                                "fiscal_year": 2018})
    assert not is_error and search["passages"], search
    samples["search_sec_filings"] = search
    for name, args in [
        ("get_company_financials", {"ticker": "MMM", "metrics": ["capital expenditure"],
                                    "period": "FY2018"}),
        ("compare_companies", {"tickers": ["TSLA", "F"], "metrics": ["revenue"],
                               "period": "FY2024"}),
        ("get_latest_filing", {"ticker": "AAPL", "filing_type": "10-Q"}),
        ("list_covered_companies", {}),
        ("verify_figures", {"answer": "3M spent $1,577 million on capex in 2018.",
                            "passage_ids": [p["id"] for p in search["passages"]]}),
    ]:
        is_error, result, ms = tool(url, name, args)
        assert not is_error, (name, result)
        samples[name] = {"arguments": args, "result": result, "ms": ms}
    report["samples"] = trimmed(samples)
    # A figure id from get_company_financials grounds a rounded, unit-converted figure.
    is_error, fact_check, _ = tool(url, "verify_figures", {
        "answer": "3M spent $1.58 billion on capex in 2018.", "passage_ids": [CAPEX_FACT]})
    assert not is_error and fact_check["grounded"] == ["$1.58 billion"], fact_check
    report["fact_verify"] = fact_check

    miss, hit = [], []
    for q in QUESTIONS:
        miss.append(tool(url, "search_sec_filings", {"question": q})[2])
    for q in QUESTIONS:
        hit.append(tool(url, "search_sec_filings", {"question": q})[2])
    report["search_latency_ms"] = {
        "cache_miss_p50": int(statistics.median(miss)), "cache_miss_max": max(miss),
        "cache_hit_p50": int(statistics.median(hit)), "n": len(QUESTIONS),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("initialize_ms", "tools_list_ms",
                                             "search_latency_ms")}, indent=2))
    print(f"verify_figures: {samples['verify_figures']['result']}")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

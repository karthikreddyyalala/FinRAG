"""Re-record the site's hero replays from the live server.

For each case: call the live MCP tool, have the eval client model write the
answer from the returned passages, then call verify_figures live. Writes
dashboard/data/recordings/<id>.json. Needs OPENAI_API_KEY in the environment.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/record_replays.py [https://<function-url>/mcp]
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from evals.client_answer import write_answer
from scripts.live_check import tool

URL = "https://ecvsxkeqdpyj5hkal7wplm2b4q0gacfh.lambda-url.us-east-1.on.aws/mcp"
OUT = Path("dashboard/data/recordings")
MODEL = "gpt-4o-mini"
EXCERPT_CHARS = 300

CASES = [
    {"id": "mmm-capex-fy2018",
     "question": "What was 3M's capital expenditure in fiscal year 2018?",
     "tool": "search_sec_filings",
     "arguments": {"question": "3M capital expenditure", "ticker": "MMM", "fiscal_year": 2018}},
    {"id": "nvda-revenue-q1fy2027",
     "question": "What was Nvidia's total revenue for the three months ended April 26, 2026?",
     "tool": "search_sec_filings",
     "arguments": {"question": "NVDA total revenue for the three months ended April 2026",
                   "ticker": "NVDA", "fiscal_year": 2026}},
    {"id": "compare-tsla-f",
     "question": "Compare Tesla and Ford total revenue in 2024.",
     "tool": "compare_companies",
     "arguments": {"tickers": ["TSLA", "F"], "metrics": ["revenue"], "period": "FY2024"}},
]


def flatten(result: dict) -> list[dict]:
    """Passages for the answer writer. XBRL figures become one-line passages with their id."""
    if "results" not in result:
        return result["passages"]
    out = []
    for ticker, company in result["results"].items():
        for f in company.get("results", []):
            if "value" in f:
                out.append({"id": f["id"], "citation": f["citation"], "ticker": ticker,
                            "form": f["source"]["form"], "filed": f["source"]["filed"],
                            "text": f"{ticker} {f['label']} {f['period']['fiscal_period']} "
                                    f"{f['period']['fiscal_year']} (period ended "
                                    f"{f['period']['end']}): {f['display']}"})
    return out


def tidy(text: str) -> str:
    """Table text with empty and repeated cells dropped, so an excerpt is readable."""
    cells = [c.strip() for c in re.split(r"\s*\|\s*|\n", text.replace("\xa0", " "))]
    kept: list[str] = []
    while cells and cells[0] == str(len(kept)):  # drop the "0 | 1 | 2 ..." column-index row
        kept.append(cells.pop(0))
    kept.clear()
    for c in cells:
        if c and (not kept or kept[-1] != c):
            kept.append(c)
    return " | ".join(kept)


def excerpt(text: str, grounded: list[str]) -> str:
    """Up to 300 chars, starting just before the first grounded figure if the passage has one."""
    clean = tidy(text)
    start = 0
    for g in grounded:
        num = re.search(r"\d[\d,.]*", g)
        if not num:
            continue
        for form in (num.group(0), num.group(0).replace(",", "")):
            at = clean.find(form)
            if at >= 0:
                start = max(0, at - 120)
                break
        else:
            continue
        break
    out = clean[start:start + EXCERPT_CHARS]
    return ("..." if start else "") + out


def record(case: dict, url: str) -> dict:
    is_error, result, tool_ms = tool(url, case["tool"], case["arguments"])
    assert not is_error, result
    passages = flatten(result)
    answer = write_answer(case["question"], passages, model=MODEL)
    is_error, verify, _ = tool(url, "verify_figures",
                               {"answer": answer, "passage_ids": [p["id"] for p in passages]})
    assert not is_error, verify
    return {
        "id": case["id"], "question": case["question"], "tool": case["tool"],
        "arguments": case["arguments"], "tool_ms": tool_ms,
        "passages": [{"id": p["id"], "citation": p["citation"], "ticker": p["ticker"],
                      "form": p["form"], "filed": p["filed"],
                      "excerpt": excerpt(p["text"], verify["grounded"])} for p in passages],
        "answer": answer, "model": MODEL,
        "verify": {"grounded": verify["grounded"], "not_found": verify["not_found"]},
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else URL
    OUT.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        rec = record(case, url)
        text = json.dumps(rec, indent=2, ensure_ascii=False)
        (OUT / f"{case['id']}.json").write_text(text + "\n")
        print(f"{case['id']}: {rec['tool_ms']} ms, verify {rec['verify']}\n{rec['answer']}\n")


if __name__ == "__main__":
    main()

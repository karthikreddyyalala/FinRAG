# FinRAG MCP: test walkthrough

How to check every part of FinRAG yourself, from a 30-second smoke test to the monitoring. Each step says what you should see. The expected results were captured from the live server on 2026-10-30.

Server URL (no sign-in):

```
https://ecvsxkeqdpyj5hkal7wplm2b4q0gacfh.lambda-url.us-east-1.on.aws/mcp
```

The server is shared. Everyone together gets 30 tool calls a minute and 1,000 a day, so wait a couple of seconds between calls.

## 1. Smoke test with curl (30 seconds, nothing to install)

```bash
U=https://ecvsxkeqdpyj5hkal7wplm2b4q0gacfh.lambda-url.us-east-1.on.aws/mcp
H=(-H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream')

# The six tools, no token
curl -s "${H[@]}" -X POST "$U" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# A real search
curl -s "${H[@]}" -X POST "$U" -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search_sec_filings","arguments":{"question":"3M capital expenditure","ticker":"MMM","fiscal_year":2018}}}'
```

(These lines are for zsh, the macOS default. In bash, `"${H[@]}"` works the same way.)

**Expect:**
- `tools/list` returns `search_sec_filings`, `get_company_financials`, `compare_companies`, `get_latest_filing`, `list_covered_companies` and `verify_figures`.
- The search returns 5 passages from `[MMM 10-K 2019-02-07]`. One of them contains the cash flow line `Purchases of property, plant and equipment (PP&E) | $ | (1,577)`.
- Warm calls take about 1 second. The first call after a quiet period can take about 15 seconds while the server loads its index.

## 2. Connect a client

**Claude Code:**

```bash
claude mcp add --transport http finrag https://ecvsxkeqdpyj5hkal7wplm2b4q0gacfh.lambda-url.us-east-1.on.aws/mcp
```

Then run `/mcp` inside Claude Code. `finrag` should show as connected with 6 tools.

**Claude (web or desktop):** add a custom connector and paste the URL. There's no sign-in step.

**Cursor:** add this to `.cursor/mcp.json`:

```json
{ "mcpServers": { "finrag": { "url": "https://ecvsxkeqdpyj5hkal7wplm2b4q0gacfh.lambda-url.us-east-1.on.aws/mcp" } } }
```

## 3. Ask questions in Claude

Ask these one at a time:

1. "Using FinRAG, what was 3M's capital expenditure in fiscal 2018? Then verify the figures."
2. "Using FinRAG, what was Nvidia's data center revenue in fiscal 2026?"
3. "Using FinRAG, compare Tesla and Ford revenue in 2024."

**Expect:**
- Claude calls a FinRAG tool, then writes the answer itself with citations like `[MMM 10-K 2019-02-07]`.
- For question 1 the figure is $1,577 million (purchases of PP&E). After you ask for verification, Claude calls `verify_figures`, which lists `$1,577 million` under `grounded`.
- For question 2, most passages come from `[NVDA 10-K 2026-02-25]`.
- If a figure isn't in the passages, Claude should say so rather than guess. The server's instructions tell it to.

## 4. Each tool, one call

| Tool | Try | Expect |
|---|---|---|
| `search_sec_filings` | `{"question": "3M capital expenditure", "ticker": "MMM", "fiscal_year": 2018}` | 5 passages from the MMM 10-K filed 2019-02-07 |
| `get_company_financials` | `{"ticker": "MMM", "metric": "capital expenditure", "period": "FY2018"}` | The first passage holds the PP&E line with `(1,577)` |
| `compare_companies` | `{"tickers": ["TSLA", "F"], "metric": "revenue", "period": "2024"}` | Passages for each ticker, including `[TSLA 10-K 2025-01-30]` |
| `get_latest_filing` | `{"ticker": "AAPL", "filing_type": "10-Q"}` | The newest Apple 10-Q from EDGAR (on 2026-10-30: filed 2026-07-31), an `sec_url`, and `in_corpus: true` |
| `list_covered_companies` | `{}` | 71 companies, each with forms and first and last filing dates |
| `verify_figures` | `{"answer": "3M spent $1,577 million on capex in 2018.", "passage_ids": [<ids from the first search>]}` | `grounded: ["$1,577 million"]`, `not_found: []` |

To call a tool from curl, use the `tools/call` body from step 1 and change `name` and `arguments`.

## 5. The guard rails

Each of these should fail cleanly, with a message that tells the client what to do:

| Try | Expect |
|---|---|
| `search_sec_filings` with `"ticker": "ZZZZ"` | Error: `ZZZZ is not in FinRAG's corpus (71 companies). Call list_covered_companies for the list.` |
| `search_sec_filings` with `"question": "   "` | Error: `question is empty.` |
| `compare_companies` with 6 tickers | Error: `Compare 2 to 5 companies.` |
| `search_sec_filings` for Apple with `"fiscal_year": 2012` | Passages from other years, plus the note `No filings matched 2012; these passages are from other years.` |
| `verify_figures` with "$9,999 million" against the 3M passage | `not_found: ["$9,999 million"]` |

## 6. Known weakness to look at

"Netflix revenue FY2023" returns quarterly 10-Q passages. The FY2023 10-K (filed 2024-01-26) is in the index but isn't ranked into the top 5. That's a ranking problem, not missing data, and the planned neural reranker targets it. Your model should still say when a passage covers a quarter rather than the full year.

## 7. Run the tests locally

From the repo root:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q        # server, retrieval, tools, infra: 278+ tests
.venv/bin/ruff check .
cd dashboard && npm run lint && npm test && npm run build
```

**Expect:** every test passes, ruff prints `All checks passed!`, and the site builds.

## 8. Full live check

This drives the deployed server the way a client would and writes the site's latency numbers:

```bash
PYTHONPATH=. .venv/bin/python scripts/live_check.py https://ecvsxkeqdpyj5hkal7wplm2b4q0gacfh.lambda-url.us-east-1.on.aws/mcp
```

It makes about 27 calls, paced at 2.5 seconds, so it takes about 2 minutes.

**Expect** numbers close to the 2026-10-30 run:
- warm search median about 0.9 s
- cache hit about 0.3 s
- `verify_figures` grounding `$1,577 million`

It writes `dashboard/data/live/live-check.json`.

## 9. Monitoring (AWS console, us-east-1)

- **Lambda > finrag-mcp-server > Monitor:** invocations every 5 minutes, even with no users. That's the health check.
- **CloudWatch > Alarms:** `finrag-mcp-server-errors` and `finrag-weekly-refresh-errors` should be `OK`. They read `INSUFFICIENT_DATA` for the first few minutes after a deploy.
- **CloudWatch > Log groups > FinragMcpServerStack-McpServerLogs...:** search for `finrag_call` to see one line per tool call (tool, arguments, latency, error). Search for `semantic search failed` to find keyword-only fallbacks. Normally there are none.
- **DynamoDB > finrag-rate-limits:** a `min#...` item and a `day#...` item, each with a running `hits` count.
- **SNS > finrag-alerts:** subscribe your email here to get alarm emails.

## 10. The website

Open [dashboard-weld-nine-28.vercel.app](https://dashboard-weld-nine-28.vercel.app) after the branch is merged and Vercel redeploys. Check that:
- the hero says no sign-in and links to `#connect`
- the counts read 71 companies, 1,082 filings and 171,790 chunks
- the tools section shows 6 tools
- the verifier demo flags a made-up figure

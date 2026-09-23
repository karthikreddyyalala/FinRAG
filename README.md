# FinRAG MCP

Cited, grounded financial intelligence over SEC filings, exposed as MCP tools any AI assistant can call.

The problem: ask Claude or ChatGPT a specific financial question and you get outdated training data, a hallucinated number stated with full confidence, or no citation to verify it against. FinRAG MCP grounds every answer in actual 10-K/10-Q/8-K filings pulled from SEC EDGAR, verifies every number in the answer against the retrieved source text, and cites the exact filing.

## Architecture

Four-stage retrieval pipeline: query rewriting (Haiku, then a deterministic GAAP line-item expansion) → parallel keyword (SQLite FTS5, BM25-ranked) + Pinecone dense search → reranking → Bedrock Sonnet generation → numerical grounding verification.

- [`diagrams/ingestion-sequence.mmd`](diagrams/ingestion-sequence.mmd) — corpus build: EDGAR → chunking → embedding → Pinecone/BM25
- [`diagrams/query-sequence.mmd`](diagrams/query-sequence.mmd) — the retrieval pipeline above, per query

## Eval results

Scored against [FinanceBench](https://huggingface.co/datasets/PatronusAI/financebench), a public benchmark of 150 financial questions with verified ground-truth answers, using [ragas](https://github.com/explodinggraphs/ragas) plus a custom numerical-grounding verifier. All 150 questions answered and all 600 ragas scoring calls completed — no partial samples.

| Metric | Score | What it measures |
|---|---|---|
| **Numerical accuracy** | **91.0%** | % of numbers in generated answers that appear verbatim in the retrieved source chunks. Our own deterministic verifier — not LLM-judged. |
| **Faithfulness** | **80.1%** | Ragas: does the answer only make claims supported by the retrieved context. |
| Answer relevancy | 15.6% | Ragas: does the answer address the question asked. |
| Context precision | 20.0% | Ragas: are the retrieved chunks actually relevant to the question. |
| Context recall | 11.3% | Ragas: did retrieval capture everything needed to answer. |

**Read this honestly, not selectively.** Numerical accuracy and faithfulness are the two metrics with no ambiguity in what they measure, and both are strong. The other three ragas metrics scored consistently low (11–20%) across every complete run of this eval, including after independently verifying that retrieval finds the exact correct source chunk and number for spot-checked questions (see `diagrams/query-sequence.mmd` for the FY2018 3M capex case that motivated several of the fixes below). The working conclusion is that ragas's LLM-judged relevance/precision/recall metrics are a poor fit for this task shape — terse numeric ground truths (`"$1577.00"`) scored against long, pipe-delimited financial table chunks — rather than a sign retrieval is actually failing 80–90% of the time. This is stated as an open question, not resolved.

### Corpus coverage

- 71 of 72 target companies ingested (10-K, 10-Q, 8-K; 2018–2026 for the 32 companies FinanceBench asks about, 2025–2026 for the remaining 40)
- **SPOT** (Spotify) has no 10-K/10-Q filings — it's a foreign private issuer that files Form 20-F, outside this project's scope by design
- **PYPL** is temporarily absent — Pinecone's free-tier monthly write-unit cap (2M) was exhausted mid-project; resets monthly. Costs exactly 1 FinanceBench question.

### Question coverage

Of the 150 FinanceBench questions: 112 ask about 10-K filings, 15 about 10-Q, 9 about 8-K — all in scope and ingested. **14 ask about earnings-call transcripts**, which this project deliberately does not ingest (third-party transcript copyright — see `CLAUDE.md` Phase 6). Realistic ceiling given current scope: 135/150 (90%), before the PYPL gap.

## Deployment

Live on AWS Lambda behind a Function URL — one MCP-compatible endpoint, no API Gateway (its 29 s integration timeout is too short for a cold-start index download).

- **Runtime:** Python 3.13, arm64/Graviton, 2048 MB, 2 min timeout, 2 GB ephemeral storage for the ~900 MB keyword index in `/tmp`
- **Auth:** bearer token, checked before any cold-start work (secrets download, Pinecone connect) so an unauthenticated probe costs nothing — interim until Cognito OAuth 2.1/PKCE
- **Secrets:** SSM Parameter Store SecureStrings, resolved at runtime; only parameter *names* appear in the CDK template, never values
- **IAM:** scoped to the keyword-index S3 prefix, the `/finrag/*` SSM path, and Anthropic Bedrock models — no wildcards
- **Bundling:** local pip install for the Lambda platform (no Docker); ships only the server's runtime deps, ~79 MB, well under the 250 MB zip limit
- **Cost at rest:** $0 — Lambda bills only on invocation, well within the free tier for personal use
- **Known limit:** this AWS account's concurrent-execution ceiling is 10 (below the standard 1000 default — a new-account throttle, same one that capped available EC2 instance types earlier in this project). Two clients invoking at the same instant can trip a transient 429; a Service Quotas increase request was rejected because it only accepts values *above* the service default, not a restore from a below-default account override. Fine for personal/demo use; would need an AWS Support ticket before any real concurrent load.

Verified end to end in a real client (Claude Desktop, not just curl): asked the canonical FinanceBench capex question, got back the correct number, correctly explained the accounting sign convention, and cited the right filing — matching the local pipeline exactly.

**Connecting a client:** clients that support remote HTTP/SSE servers natively (`{"url": ..., "headers": {...}}` in their MCP config) can point straight at the Function URL. Claude Desktop's local build does not — its config only accepts local `command`/`args` (stdio) servers, so remote servers need a bridge. [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) does this:

```json
{
  "mcpServers": {
    "finrag": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "<Function URL>/mcp", "--header-file", "/path/to/headers.txt"]
    }
  }
}
```

where `headers.txt` holds one line, `Authorization: Bearer <token>` — a file, not `--header` inline, so the token never appears in the process list (`ps`). `mcp-remote` always attempts OAuth discovery first even with static headers; it fails over to the header-only path but that can add real latency on a Lambda cold start.

## What's built vs. what's next

| | Status |
|---|---|
| Ingestion pipeline (EDGAR → chunk → embed → Pinecone/FTS5) | Done |
| Four-stage retrieval + numerical verification | Done |
| Eval harness (FinanceBench, ragas, CI gate) | Done |
| AWS deployment (Lambda + Function URL) | **Done** — see Deployment above |
| Remaining 3 of 4 MCP tools | Not started |
| Cognito auth, observability dashboard | Not started |

See `CLAUDE.md` for the full week-by-week build plan and current state.

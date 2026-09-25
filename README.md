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

### Baseline comparison

Same 150 FinanceBench questions, three retrieval configurations. Baselines run with no query rewriting and no CrossEncoder/lexical reranking — Baseline A takes Pinecone's raw top-k dense matches, Baseline B takes the keyword index's raw top-k BM25 matches, both straight into generation.

| Metric | Baseline A (dense only) | Baseline B (BM25 only) | Full pipeline |
|---|---|---|---|
| Numerical accuracy | 86.5% | **94.4%** | 91.0% |
| Faithfulness | 79.4% | **83.8%** | 80.1% |
| Answer relevancy | 16.1% | 10.1% | 15.6% |
| Context precision | 14.1% | 14.2% | 20.0% |
| Context recall | 10.8% | 14.1% | **11.3%** |

**Read honestly:** on this benchmark, BM25-only retrieval alone scores *higher* than the full four-stage pipeline on numerical accuracy and faithfulness. FinanceBench's questions are largely verbatim-keyword-friendly ("FY2018 capital expenditure" appears close to how the filing states it once GAAP-synonym expansion isn't needed to match), which favors lexical search directly. What the full pipeline demonstrably buys over dense-only search is the +4.5pt numerical accuracy and +2.9pt context recall gap versus Baseline A — hybrid retrieval and query rewriting help most exactly where dense embeddings alone miss a keyword-heavy, jargon-laden financial term. Whether the added complexity (rewrite + hybrid + rerank) is worth it over BM25 alone specifically for FinanceBench-style questions is an open, honest finding, not a foregone conclusion — a harder or more paraphrased query set would likely widen the gap in the full pipeline's favor.

One real bug surfaced by running Baseline B: unlike the full pipeline, BM25-only retrieval has no dense/rerank pass to screen out an oversized match, and `chunker.py` exempts table chunks from its ~1500-word target (one table = one chunk, regardless of size). A large schedule table blew Sonnet's context window outright (`ValidationException: Input is too long for requested model`) at question 91/150. Fixed at the shared `generate_answer()` call, not per-baseline, since any retrieval path can hand it an oversized chunk — see `server/generation/answer_generator.py`'s `MAX_CHUNK_CHARS` cap.

### Corpus coverage

- 71 of 72 target companies ingested (10-K, 10-Q, 8-K; 2018–2026 for the 32 companies FinanceBench asks about, 2025–2026 for the remaining 40)
- **SPOT** (Spotify) has no 10-K/10-Q filings — it's a foreign private issuer that files Form 20-F, outside this project's scope by design
- **PYPL** is temporarily absent — Pinecone's free-tier monthly write-unit cap (2M) was exhausted mid-project; resets monthly. Costs exactly 1 FinanceBench question.

### Question coverage

Of the 150 FinanceBench questions: 112 ask about 10-K filings, 15 about 10-Q, 9 about 8-K — all in scope and ingested. **14 ask about earnings-call transcripts**, which this project deliberately does not ingest (third-party transcript copyright — see `CLAUDE.md` Phase 6). Realistic ceiling given current scope: 135/150 (90%), before the PYPL gap.

## Deployment

Live on AWS Lambda behind a Function URL — one MCP-compatible endpoint, no API Gateway (its 29 s integration timeout is too short for a cold-start index download).

- **Runtime:** Python 3.13, arm64/Graviton, 2048 MB, 2 min timeout, 2 GB ephemeral storage for the ~900 MB keyword index in `/tmp`
- **Auth:** Cognito OAuth 2.1/PKCE only, checked before any cold-start work (secrets download, Pinecone connect) so an unauthenticated probe costs nothing. (An interim static bearer token existed during early deployment and was retired once Cognito login was verified end to end from a real client.)
- **Secrets:** SSM Parameter Store SecureStrings, resolved at runtime; only parameter *names* appear in the CDK template, never values
- **IAM:** scoped to the keyword-index S3 prefix, the `/finrag/*` SSM path, and Anthropic Bedrock models — no wildcards
- **Bundling:** local pip install for the Lambda platform (no Docker); ships only the server's runtime deps, ~79 MB, well under the 250 MB zip limit
- **Cost at rest:** $0 — Lambda bills only on invocation, well within the free tier for personal use
- **Known limit:** this AWS account's concurrent-execution ceiling is 10 (below the standard 1000 default — a new-account throttle, same one that capped available EC2 instance types earlier in this project). Two clients invoking at the same instant can trip a transient 429; a Service Quotas increase request was rejected because it only accepts values *above* the service default, not a restore from a below-default account override. Fine for personal/demo use; would need an AWS Support ticket before any real concurrent load.

Verified end to end in a real client (Claude Desktop, not just curl): asked the canonical FinanceBench capex question, got back the correct number, correctly explained the accounting sign convention, and cited the right filing — matching the local pipeline exactly.

**Connecting a client:** clients that support remote HTTP/SSE servers natively (`{"url": ..., "headers": {...}}` in their MCP config) can point straight at the Function URL. Claude Desktop's local build does not — its config only accepts local `command`/`args` (stdio) servers, so remote servers need a bridge. [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) does this.

**Cognito OAuth 2.1/PKCE is the only accepted credential** — a single-user Cognito pool, a public PKCE app client (no client secret), and the `/.well-known/oauth-protected-resource` discovery endpoint a client needs to find it are all live and verified end to end in Claude Desktop. (An earlier interim static bearer token was retired once that login flow was confirmed working from a real client — see `CLAUDE.md` Phase 11, item A3.)

```json
{
  "mcpServers": {
    "finrag": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "<Function URL>/mcp",
        "--static-oauth-client-info", "{\"client_id\":\"5n9n0e2ugjnklckjlrtc50p9c4\"}",
        "--static-oauth-client-metadata", "{\"scope\":\"openid finrag/invoke\",\"token_endpoint_auth_method\":\"none\"}"
      ]
    }
  }
}
```

**Why not just drop `--header-file` and let `mcp-remote` discover everything on its own** (the original plan): `mcp-remote` defaults to OAuth Dynamic Client Registration (RFC 7591), which Cognito doesn't support — it only works with a pre-registered app client, hence `--static-oauth-client-info` pointing at the one this stack creates.

Two more bugs only showed up live, past that first one:
- Cognito's hosted UI returned a bare "An error was encountered with the requested page" with no explanation. Root cause: `mcp-remote` derives its local OAuth callback port from a hash of the server URL (`11164` for this Function URL, not a fixed default), and the CDK-registered callback URL had a different, guessed port (`8090`). Fixed by reading the actual port from `mcp-remote`'s own log and registering that.
- Then `invalid_request - invalid_scope`: the app client only allowed our custom `finrag/invoke` scope, but `mcp-remote`'s default authorize request always asks for `openid email phone profile` too, and Cognito rejects the whole request if any requested scope isn't explicitly allowed. Fixed by adding the four standard OIDC scopes to the app client.

Two more client-side settings, both in `--static-oauth-client-metadata`:
- `scope`: `mcp-remote` picks scopes from Cognito's discovery metadata, which only lists the standard OIDC ones — never custom resource-server scopes. Without pinning `finrag/invoke`, login succeeds but every request gets a 401, and `mcp-remote` deletes the cached token and gives up.
- `token_endpoint_auth_method: none`: Cognito's metadata only advertises `client_secret_basic/post`, so `mcp-remote` would try to authenticate the token exchange with a secret this public PKCE client doesn't have.

Claude Desktop reads this config only at launch — after editing it, fully quit (Cmd+Q), don't just close the window.

First login prompts you to set a permanent password for `karthikreddyy386@gmail.com`. Once you've confirmed it works end to end in Claude Desktop, the static token path gets retired.

## What's built vs. what's next

| | Status |
|---|---|
| Ingestion pipeline (EDGAR → chunk → embed → Pinecone/FTS5) | Done |
| Four-stage retrieval + numerical verification | Done |
| Eval harness (FinanceBench, ragas, CI gate) | Done |
| AWS deployment (Lambda + Function URL) | **Done** — see Deployment above |
| All 4 MCP tools (search, financials, compare, latest filing) | **Done** — live-tested |
| Cognito OAuth 2.1/PKCE | **Deployed, dual-accept** — see below; needs a human login to confirm |
| EventBridge weekly refresh | **Deployed** — diffs EDGAR against cache, ingests only what's new |
| Observability dashboard | Not started |

See `CLAUDE.md` for the full week-by-week build plan and current state.

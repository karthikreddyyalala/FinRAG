# FinRAG MCP

An MCP server that answers questions about public companies from their SEC filings, with sources.

Plug it into Claude, Cursor or any MCP client. Ask "What was Netflix's revenue in 2023?" and you get $33,723.3 million, the filing it came from and a link, not a number the model half-remembers.

**Site:** [dashboard-weld-nine-28.vercel.app](https://dashboard-weld-nine-28.vercel.app)

## Connect

No sign-in needed. Server URL:

```
https://ecvsxkeqdpyj5hkal7wplm2b4q0gacfh.lambda-url.us-east-1.on.aws/mcp
```

- **Claude (web or desktop):** Customize > Connectors > Add custom connector, paste the URL.
- **Claude Code:** `claude mcp add --transport http finrag <url>`
- **Cursor:** add to `.cursor/mcp.json`:

  ```json
  { "mcpServers": { "finrag": { "url": "<url>" } } }
  ```

Usage is shared: 30 tool calls a minute and 1,000 a day across everyone.

[WALKTHROUGH.md](WALKTHROUGH.md) walks through every tool with example questions.

## Tools

| Tool | What it does |
|---|---|
| `get_company_financials` | Exact reported figures (revenue, net income, capex, ...) for any US-listed company, from SEC's XBRL data |
| `compare_companies` | The same figures for 2 to 5 companies side by side |
| `search_sec_filings` | The 5 most relevant passages from 10-K, 10-Q and 8-K filings for 71 large companies |
| `verify_figures` | Checks every number in an answer against the sources and flags the ones it can't find |
| `get_latest_filing` | The newest filing of a given type, straight from EDGAR |
| `list_covered_companies` | Which companies, forms and years the search covers |

The server never writes answers itself. Your client's model writes the answer from what the tools return.

## How it works

- **Figures** come from SEC's free XBRL API. The tricky parts are handled: old years repeated inside newer 10-Ks, amended filings, Q4 (no filing reports it on its own, so it's full year minus nine months and labelled as such), and year-to-date cash flows.
- **Search** is hybrid: keyword search (SQLite FTS5) and vector search (Pinecone, OpenAI embeddings) each return 40 candidates, then Voyage's reranker picks the best 5. Filing tables are cleaned up first so the model can tell which number belongs to which year.
- **Fallbacks:** if embeddings fail, search runs on keywords only. If the reranker is down, or past its daily cap, a simpler word-overlap ranking takes over. Either way the result says so.
- **Corpus:** 1,082 filings, about 172,000 chunks, refreshed weekly from EDGAR.

It runs on AWS Lambda with DynamoDB for rate limits, caching and call logs, plus a health check every 5 minutes. [diagrams/](diagrams/) has the full sequence diagrams.

## Results

The test that matters is the one that matches real use: a model (gpt-4o-mini) calls the live tools in a loop, the way Claude or Cursor would, and each answer is marked right, wrong or refused.

| FinanceBench (110 questions with a numeric answer) | Search only | Search + figures (live) |
|---|---|---|
| Right | 67 | **92** |
| Wrong | 21 | **14** |
| Refused | 22 | **4** |

On 48 questions I checked by hand against the filings, the score went from 13 right / 32 wrong / 3 refused to **39 / 7 / 2**. Most of them ask for a fourth quarter, which search alone kept getting wrong.

Where it still misses:
- Judgment questions ("is Verizon capital intensive?") that the automatic grader scores on a single number.
- Ratios where the model picks a different formula from the answer key.
- Segment and bank figures that only appear in passages, and non-GAAP numbers, which XBRL doesn't carry.

Speed on the live server: a search takes about 1 s, figures take about 3 s the first time a company is asked for and 0.3 s after that. The first call after a deploy takes about 15 s.

Every earlier measurement, including what was wrong with past numbers and how it was fixed, is in [CHANGELOG.md](CHANGELOG.md).

## Testing

- **Unit tests:** 359 tests in `tests/unit/` cover the XBRL parsing, retrieval, reranker, verifier, tools, rate limits, caching and the AWS stacks. Run them with `pytest tests/unit`. CI runs them plus lint and the site build on every PR.
- **Evals:** `evals/run_agentic.py` runs the end-to-end test above (about $0.35 in OpenAI plus Voyage), and `evals/retrieval_eval.py` measures retrieval on its own. Results are saved in `evals/results/`.
- **Live check:** `scripts/live_check.py` calls the deployed server and records latency.

## Run your own

You need an AWS account, Node 20+, Python 3.12+, and API keys for OpenAI, Pinecone and Voyage (Voyage needs a card on file). Everything deploys to us-east-1.

1. Create a Pinecone serverless index `finrag-filings` (1536 dimensions, cosine).
2. Install:
   ```bash
   git clone https://github.com/karthikreddyyalala/FinRAG.git && cd FinRAG
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. S3 bucket names are global, so rename them, and set `SEC_USER_AGENT` in `pipeline/edgar_client.py` to your name and email:
   ```bash
   perl -pi -e 's/finrag-(raw|processed)-filings/yourname-$1-filings/g' $(git grep -lE 'finrag-(raw|processed)-filings' -- '*.py')
   ```
4. Store the keys (all three are required):
   ```bash
   aws ssm put-parameter --region us-east-1 --type SecureString --name /finrag/openai-api-key --value <key>
   aws ssm put-parameter --region us-east-1 --type SecureString --name /finrag/pinecone-api-key --value <key>
   aws ssm put-parameter --region us-east-1 --type SecureString --name /finrag/voyage-api-key --value <key>
   ```
5. Deploy (`-c alert_email` is optional and emails you when alarms fire):
   ```bash
   npx aws-cdk bootstrap aws://<account-id>/us-east-1
   npx aws-cdk deploy --all --require-approval never -c alert_email=you@example.com
   ```
6. Build the corpus. This takes hours and a few dollars of embeddings, and resumes if it stops:
   ```bash
   export OPENAI_API_KEY=<key> PINECONE_API_KEY=<key>
   PYTHONPATH=. python scripts/bootstrap_corpus.py
   aws s3 sync evals/results/chunk_cache s3://yourname-processed-filings/chunk_cache/
   ```
7. Point your client at the `McpEndpoint` output.

## Limits

- Passage search covers 71 companies, mostly filings from 2022 on. Figures cover any company with XBRL data (about 2009 on).
- No earnings call transcripts, and no 20-F filers (e.g. Spotify).
- Answer quality depends on your client's model, since it does the writing.

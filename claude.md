# FinRAG MCP — Complete Project Constitution for Claude Code

Hey Claude. I am Karthik and I am building FinRAG MCP from scratch.
This file contains everything you need. Read it fully before doing anything.

Before writing a single line of code, do this in exact order:
1. Read this entire file top to bottom
2. Generate all architecture diagrams (sequence, component, data flow)
3. Verify every package in the stack is current and compatible
4. Confirm the full plan step by step with me
5. Then implement week by week, writing tests alongside every module

Do not skip any phase. Do not write implementation code before diagrams
and verification are done and confirmed by me.

---

## Phase 0: What This Project Is

### The Problem

Every public US company files quarterly (10-Q) and annual (10-K) reports
with the SEC. These filings contain the most accurate, legally verified
financial data that exists: revenue breakdowns, margin trends, management
commentary, risk factors, forward guidance.

When a finance analyst asks Claude or ChatGPT "How did Nvidia data center
revenue change from Q1 2024 to Q1 2026?", they get one of three bad outcomes:

1. Outdated training data with no current filings
2. Hallucinated revenue figures stated with full confidence
3. Zero citations to any source document

FinRAG MCP fixes all three. It gives any MCP-compatible AI assistant
(Claude Desktop, Cursor, ChatGPT with MCP, custom enterprise agents)
accurate, cited, up-to-date answers grounded in actual SEC filings.

### What It Is

Two things combined:

Thing 1: A financial document database
- 500+ SEC filings across 50 companies downloaded from EDGAR (free public API)
- Processed with table-aware extraction (BeautifulSoup + pandas)
- Chunked hierarchically and embedded into Pinecone vector store
- Refreshed weekly via EventBridge cron

Thing 2: An MCP server exposing that database as tools
- Any AI client that speaks MCP connects once and gets financial intelligence
- Four tools: search_sec_filings, get_company_financials, compare_companies, get_latest_filing
- Every answer includes citations: {ticker, filing_type, period, page}
- Every number in every answer is verified against source chunks

### How It Is Different

| | FinRAG MCP | Plain Claude/ChatGPT | Generic RAG Demo |
|---|---|---|---|
| Data source | Actual SEC filings | Training data | Uploaded PDFs |
| Current data | Yes, weekly refresh | No, knowledge cutoff | No, static |
| Table handling | BeautifulSoup structured | Poor | Poor |
| Citations | Exact filing + page | None | Approximate |
| Eval harness | FinanceBench 300Q | None | None |
| Multi-client | Any MCP client | Locked to one app | Custom UI only |
| Cost per query | Tracked and optimized | Unknown | Unknown |
| Number verification | Yes, custom verifier | No | No |

---

## Phase 1: Full Tech Stack (Cost-Optimized)

### Stack Decision Table

| Layer | Tool | Cost | Why |
|---|---|---|---|
| Language | Python 3.12 | Free | Latest stable |
| MCP protocol | official `mcp` Python SDK | Free | Anthropic standard |
| API framework | FastAPI + Mangum | Free | Standard for AI backends, Lambda compatible |
| Document processing | BeautifulSoup4 + lxml + pandas | Free | EDGAR filings are served as HTML, not PDF; pdfplumber cannot read them |
| Embeddings | Amazon Titan Text Embeddings V2 | ~$0.02/1M tokens (no free tier) | Native Bedrock; cost is trivial (~$0.25 one-time for initial 500-filing corpus) |
| Vector store | Pinecone free tier (pip package: pinecone, not pinecone-client) | Free | Replaces OpenSearch Serverless ($100/mo) |
| Keyword search | rank-bm25 in-memory | Free | No separate search service needed |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 | Free | HuggingFace, runs inside Lambda |
| Query rewriting | Claude Haiku 4.5 via Bedrock | Free tier | Cheap, fast |
| Generation | Claude Sonnet 4.5 via Bedrock | Free tier | Best financial reasoning |
| Auth | Amazon Cognito OAuth 2.1 + PKCE | Free | Production standard |
| Hosting | AWS Lambda + API Gateway | Free tier | Serverless, scales to zero |
| Storage | S3 | ~$3/mo | Standard |
| Logging | DynamoDB + CloudWatch | Free tier | Query history + metrics |
| Evals | ragas + custom numerical verifier | Free | Benchmark against FinanceBench |
| CI | GitHub Actions | Free (public repo) | Eval gate on every PR |
| Dashboard | Next.js + Recharts on Vercel | Free | Public eval metrics |
| IaC | AWS CDK Python | Free | Reproducible infrastructure |
| Data source | SEC EDGAR API | Free, no auth | Ground truth financial data |
| Ingestion cron | AWS EventBridge | Free tier | Weekly corpus refresh |

Total cost target: under $5/month

### Why Each Cost Decision Was Made

BeautifulSoup + pandas over pdfplumber:
SEC EDGAR serves 10-Q/10-K filings as HTML, not PDF — pdfplumber can only
read PDF bytes and has nothing valid to process here. BeautifulSoup + pandas
read the HTML natively, for free, with no extra conversion step.

Pinecone over OpenSearch Serverless:
OpenSearch Serverless charges $100/month baseline even with zero queries.
Pinecone free tier gives 1 index, 2GB storage, enough for 500 filings.
Use Pinecone.

CrossEncoder over Cohere Rerank:
Cohere Rerank via Bedrock has per-call costs.
cross-encoder/ms-marco-MiniLM-L-6-v2 from HuggingFace runs locally inside Lambda.
Performance is comparable for financial text. Use CrossEncoder.

rank-bm25 over Elasticsearch:
No separate service needed. Runs in Lambda memory.
For 500 filings it is fast enough. Use rank-bm25.

---

## Phase 2: Repository Structure

Create exactly this structure. Do not add files outside it without asking.

```
finrag-mcp/
├── CLAUDE.md                          # This file
├── README.md                          # Architecture diagram, setup, demo link
│
├── infra/                             # AWS CDK infrastructure as code
│   ├── app.py                         # CDK app entry point
│   └── stacks/
│       ├── storage_stack.py           # S3 buckets, DynamoDB tables
│       ├── pinecone_stack.py          # Pinecone index configuration
│       ├── mcp_server_stack.py        # Lambda, API Gateway, Cognito
│       └── observability_stack.py     # CloudWatch dashboards, X-Ray
│
├── pipeline/                          # Data ingestion pipeline
│   ├── edgar_client.py                # EDGAR API downloader (boto3 + requests)
│   ├── html_processor.py               # BeautifulSoup + pandas table/text extraction
│   ├── chunker.py                     # Hierarchical chunking with metadata
│   ├── ingestion_handler.py           # Lambda handler for ingestion trigger
│   └── sync_pinecone.py               # Push chunks to Pinecone with embeddings
│
├── server/                            # MCP server
│   ├── main.py                        # FastAPI app entry point + MCP registration
│   ├── mcp_tools/
│   │   ├── search_filings.py          # search_sec_filings tool
│   │   ├── get_financials.py          # get_company_financials tool
│   │   ├── compare_companies.py       # compare_companies tool (multi-hop)
│   │   └── get_latest_filing.py       # get_latest_filing tool
│   ├── retrieval/
│   │   ├── query_rewriter.py          # Haiku query rewriting
│   │   ├── hybrid_retriever.py        # Parallel BM25 + Pinecone dense search
│   │   ├── reranker.py                # CrossEncoder reranking (top 20 → top 5)
│   │   └── numerical_verifier.py      # Number grounding checker
│   ├── generation/
│   │   └── answer_generator.py        # Bedrock Converse API + citation formatter
│   ├── auth/
│   │   └── cognito_validator.py       # JWKS token validation middleware
│   └── observability/
│       └── logger.py                  # DynamoDB + CloudWatch logging per query
│
├── evals/                             # Evaluation harness
│   ├── datasets/
│   │   ├── financebench_150.json      # FinanceBench questions + ground truth
│   │   └── custom_150.json            # Custom curated questions (write in Week 3)
│   ├── metrics/
│   │   ├── ragas_metrics.py           # faithfulness, relevance, precision, recall
│   │   └── numerical_accuracy.py      # Custom number grounding metric
│   ├── run_eval.py                    # Full 300-question eval runner
│   ├── run_ci_eval.py                 # 30-question CI subset runner
│   └── results/                       # Historical eval results JSON (gitignored)
│
├── dashboard/                         # Public Vercel eval dashboard
│   ├── pages/
│   │   └── index.tsx                  # Main metrics page
│   └── components/
│       ├── EvalScoreChart.tsx          # ragas scores over time (Recharts)
│       ├── CostPerQueryChart.tsx       # Cost per query over time
│       └── LatencyBreakdown.tsx        # Per-stage latency breakdown
│
├── scripts/
│   ├── bootstrap_corpus.py            # One-time: download initial 20 company filings
│   └── weekly_refresh.py              # EventBridge cron target
│
├── tests/
│   ├── unit/                          # Unit test per module (write alongside code)
│   └── integration/                   # Live AWS integration tests
│
├── .github/
│   └── workflows/
│       ├── ci.yml                     # Lint + unit tests + 30Q eval on every PR
│       └── nightly_eval.yml           # Full 300Q eval on weekly cron
│
├── requirements.txt                   # Python dependencies
├── pyproject.toml                     # Project config + linting rules
└── docker-compose.yml                 # Local development environment
```

---

## Phase 3: Full Data Flow

### Ingestion Flow (runs once, then weekly via EventBridge)

```
Step 1: edgar_client.py hits EDGAR API
        URL: https://data.sec.gov/submissions/CIK{company_cik}.json
        Downloads: last 4 quarters 10-Q + last 2 years 10-K per company
        Stores raw PDFs: s3://finrag-raw/{ticker}/{filing_type}/{date}.pdf
        No auth required. Free. Rate limit: 10 requests/second max.

Step 2: html_processor.py processes each filing with BeautifulSoup + pandas
        Extracts: text blocks preserving section headers
        Extracts: tables as structured JSON preserving row/column relationships
        Stores processed: s3://finrag-processed/{ticker}/{filing_type}/{date}.json
        Format: {text_blocks: [...], tables: [{headers: [], rows: [[]]}], metadata: {}}

Step 3: chunker.py applies hierarchical chunking
        Parent chunks: full sections at 1500 tokens
        Child chunks: paragraphs within sections at 400 tokens
        Table chunks: each table as one chunk with structured metadata
        Every chunk tagged: {ticker, company_name, filing_type, period, section, page_number, chunk_type}

Step 4: sync_pinecone.py embeds and upserts all chunks
        Calls Bedrock Titan Embeddings V2 for each chunk
        Upserts to Pinecone with full metadata
        Also builds in-memory BM25 index from chunk text (serialized to S3 for reuse)
        Sync complete: corpus ready for queries
```

### Query Flow (every user question, end to end)

```
Step 1: MCP client calls tool search_sec_filings
        Input: {query: "How did Nvidia data center revenue change Q1 2024 to Q1 2026?"}
        Transport: JSON-RPC 2.0 over HTTP/SSE

Step 2: cognito_validator.py validates OAuth 2.1 Bearer token
        Fetches JWKS from Cognito endpoint
        Validates signature, expiry, and scope
        Rejects if invalid. Returns 401.

Step 3: query_rewriter.py sends query to Haiku via Bedrock
        System prompt: "Expand ticker symbols to company names.
                        Extract time constraints. Optimize for financial document retrieval.
                        Return rewritten query only."
        Output: "Nvidia Corporation NVDA data center segment revenue Q1 2024 Q1 2026 10-Q quarterly report"

Step 4: hybrid_retriever.py runs parallel retrieval
        Thread A: BM25 search on in-memory index → top 10 chunks by keyword relevance
        Thread B: Pinecone query with Titan embedding of rewritten query → top 10 chunks by semantic similarity
        Merge: combine 20 results, deduplicate by chunk_id
        Result: up to 20 unique candidate chunks

Step 5: reranker.py sends candidates to CrossEncoder
        Model: cross-encoder/ms-marco-MiniLM-L-6-v2 (runs inside Lambda)
        Input: [(original_query, chunk_text) for chunk in candidates]
        Output: top 5 chunks ranked by true relevance score
        Result: 5 most relevant chunks with metadata

Step 6: answer_generator.py calls Bedrock Converse API
        Model: Claude Sonnet 4.5
        System prompt enforces:
          - Cite every claim with {ticker, filing_type, period, page}
          - Never state a number not present verbatim in the provided context
          - If context is insufficient, say so explicitly. Do not guess.
          - Format citations inline as [NVDA 10-Q Q1-2026 p.23]
        Input: top 5 chunks + system prompt + original user query
        Output: answer with inline citations

Step 7: numerical_verifier.py scans the generated answer
        Extracts all numbers using regex: dollars, percentages, large numbers
        Normalizes formats: "$23.4B" == "23,400 million" == "23.4 billion"
        For each number: checks if it appears (in any format) in any of the 5 source chunks
        If number not found in sources: removes it and adds qualifier "exact figure unavailable in retrieved context"
        Returns verified answer

Step 8: logger.py logs everything to DynamoDB + CloudWatch
        Logs: {query, rewritten_query, bm25_chunks, pinecone_chunks,
               reranked_chunks, final_answer, tokens_in, tokens_out,
               cost_usd, latency_ms_per_stage, timestamp, user_id}

Step 9: MCP server returns response to client
        {answer: "...", citations: [{ticker, filing_type, period, page}],
         cost_usd: 0.008, latency_ms: 3200}

Step 10: Claude Desktop / Cursor renders answer with citations in chat
```

---

## Phase 4: Evaluation Harness

### Golden Dataset (300 questions total)

FinanceBench 150 (download from github.com/patronusai/financebench):
- Real financial questions with verified ground truth answers
- Covers revenue, margins, EPS, cash flow, segment breakdowns
- Companies already covered: AAPL, MSFT, AMZN, GOOGL, META, NVDA, TSLA + more

Custom 150 (write these in Week 3):
- 50 single-company single-metric (easy): "What was Apple total revenue in Q3 2025?"
- 50 single-company multi-metric (medium): "How did Apple gross margin and operating margin trend across 2024?"
- 30 multi-company comparison (hard): "Compare Tesla and Ford gross margins across 2024 and 2025"
- 20 table-specific (hardest): "What was the exact breakdown of Nvidia revenue by geography in Q4 2025?"

### ragas Metrics (all scored 0.0 to 1.0)

```python
faithfulness        # Answer only claims things supported by retrieved context
answer_relevance    # Answer actually addresses the question asked
context_precision   # Retrieved chunks are genuinely relevant to the question
context_recall      # Retrieval captured all the information needed to answer
numerical_accuracy  # Custom: % of numbers in answer that appear verbatim in source chunks
```

### CI Pipeline (GitHub Actions — runs on every PR)

```yaml
name: CI Eval
on: [pull_request]
jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - name: Lint and unit tests
        run: pytest tests/unit/ && ruff check .
      - name: Run 30-question CI eval
        run: python evals/run_ci_eval.py
      - name: Check faithfulness threshold
        run: python -c "import json; r=json.load(open('evals/results/ci_latest.json')); assert r['faithfulness'] >= 0.85, f'faithfulness {r[\"faithfulness\"]} < 0.85'"
      - name: Check numerical accuracy threshold
        run: python -c "import json; r=json.load(open('evals/results/ci_latest.json')); assert r['numerical_accuracy'] >= 0.90, f'numerical_accuracy {r[\"numerical_accuracy\"]} < 0.90'"
      - name: Post scores as PR comment
        # Post all metric scores as a comment on the PR
```

### Baseline Comparison (run in Week 3, publish in README)

Run same 300 questions against:
- Baseline A: Pinecone dense search only, no query rewriting, no reranking
- Baseline B: BM25 only, no dense search, no reranking
- Your system: full four-stage pipeline

Publish comparison table in README. This proves your engineering decisions improved quality.

---

## Phase 5: MCP Tools Specification

### Tool 1: search_sec_filings
```
Input:  query (str) — natural language financial question
Output: answer (str), citations (list), cost_usd (float), latency_ms (int)
Flow:   full four-stage pipeline (rewrite → hybrid → rerank → generate → verify)
```

### Tool 2: get_company_financials
```
Input:  ticker (str), metric (str), period (str)
        Example: ticker="NVDA", metric="revenue", period="Q1-2026"
Output: structured financial data with exact source citation
Flow:   targeted retrieval optimized for specific metric lookup
```

### Tool 3: compare_companies
```
Input:  tickers (list[str]), metric (str), period (str)
        Example: tickers=["TSLA","F"], metric="gross_margin", period="2024-2025"
Output: side-by-side comparison with citations per company
Flow:   multi-hop retrieval (separate query per company, merged answer)
```

### Tool 4: get_latest_filing
```
Input:  ticker (str), filing_type (str)
        Example: ticker="AAPL", filing_type="10-Q"
Output: metadata of most recent filing + 3-sentence executive summary
Flow:   metadata lookup + brief summarization, no full RAG pipeline
```

---

## Phase 6: Target Corpus

Start with 20 companies in Week 1. Expanded to 50 in Week 2.

Tech (5): NVDA, AAPL, MSFT, GOOGL, META
EV/Auto (5): TSLA, F, GM, RIVN, LCID
Finance (5): JPM, BAC, GS, MS, V
Healthcare (5): JNJ, PFE, UNH, ABBV, MRK
Energy (5): XOM, CVX, COP, SLB, OXY
Consumer Retail (5): WMT, COST, HD, TGT, LOW
Industrials (5): BA, CAT, GE, HON, UPS
Telecom (5): T, VZ, TMUS, CMCSA, CHTR
Media (5): DIS, NFLX, WBD, PARA, SPOT
Semiconductors (5): AMD, INTC, QCOM, TXN, AVGO

Per company ingest:
- Last 4 quarters of 10-Q (quarterly reports)
- Last 2 years of 10-K (annual reports)
- Do NOT ingest earnings call transcripts (copyright issues with third-party sources)

EDGAR CIK lookup: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={ticker}&type=10-Q

---

## Phase 7: Week by Week Build Plan

### Week 1: Foundation (goal: working in Claude Desktop)

Tasks in order:
- [ ] Initialize repo, push to GitHub (public from day 1)
- [ ] AWS CDK: deploy storage_stack (S3 buckets + DynamoDB table)
- [ ] edgar_client.py: download 10-Q and 10-K for 20 companies into S3
- [ ] html_processor.py: BeautifulSoup + pandas extraction for text + tables
- [ ] chunker.py: basic hierarchical chunking with metadata
- [ ] sync_pinecone.py: embed with Titan + upsert to Pinecone
- [ ] server/main.py: bare FastAPI app with MCP registration
- [ ] mcp_tools/search_filings.py: one tool, direct Pinecone query only (no reranking yet)
- [ ] Deploy to Lambda via CDK
- [ ] Connect to Claude Desktop and test 5 manual queries

STOP after Week 1. Verify Claude Desktop returns answers before starting Week 2.

### Week 2: Retrieval Quality

Tasks in order:
- [x] query_rewriter.py: Haiku-powered query expansion
- [x] hybrid_retriever.py: parallel BM25 + Pinecone with merge/dedup
- [x] reranker.py: CrossEncoder top 20 → top 5
- [x] numerical_verifier.py: number extraction + source verification
- [x] citation formatter in answer_generator.py
- [x] Expand corpus to 50 companies
- [ ] Test 20 manual financial questions, check citation accuracy (Task 9 -- manual, needs live deploy)

### Week 3: Eval Harness

Tasks in order:
- [ ] Download FinanceBench from github.com/patronusai/financebench
- [ ] Write 150 custom questions with ground truth answers (custom_150.json)
- [ ] ragas_metrics.py: wire up all four ragas metrics
- [ ] numerical_accuracy.py: custom verifier metric
- [ ] run_ci_eval.py: 30-question subset runner
- [ ] run_eval.py: full 300-question runner
- [ ] GitHub Actions ci.yml: lint + test + 30Q eval on every PR
- [ ] Run first full eval, record baseline numbers
- [ ] Run Baseline A and Baseline B for comparison table

### Week 4: Observability and Cost

Tasks in order:
- [ ] logger.py: log every query stage to DynamoDB + CloudWatch
- [ ] Add prompt caching on Bedrock Converse API calls
- [ ] Add query result caching in DynamoDB (hash query → cache hit)
- [ ] Model tier routing: simple single-metric → Haiku, complex comparison → Sonnet
- [ ] Next.js dashboard on Vercel: EvalScoreChart, CostPerQueryChart, LatencyBreakdown
- [ ] Publish before/after cost numbers in README

### Week 5: Production Hardening

Tasks in order:
- [ ] cognito_validator.py: JWKS-based OAuth 2.1 token validation
- [ ] API Gateway rate limiting (100 req/min per client)
- [ ] get_financials.py, compare_companies.py, get_latest_filing.py tools
- [ ] EventBridge weekly refresh cron wired to weekly_refresh.py
- [ ] Full README with architecture diagram (use finrag-mcp-sequence.mmd)
- [ ] Submit to official MCP registry (modelcontextprotocol.io/registry)

### Week 6: Polish

Tasks in order:
- [ ] Record 3-minute demo video (Claude Desktop + Cursor side by side)
- [ ] Write technical blog post: "What I learned building production RAG on AWS Bedrock"
- [ ] Post on r/LocalLLaMA, r/LangChain, Hacker News Show HN
- [ ] Verify all dashboard links work
- [ ] Final README pass

---

## Phase 8: Code Standards (non-negotiable)

Every file must follow these rules. No exceptions.

```python
# Type hints on every function
def search_filings(query: str, top_k: int = 5) -> list[dict]:

# Docstring on every class and public method
def rerank(self, query: str, chunks: list[str]) -> list[dict]:
    """
    Rerank candidate chunks using CrossEncoder.
    
    Args:
        query: Original user query for relevance scoring
        chunks: List of candidate chunk texts from hybrid retrieval
    
    Returns:
        Top 5 chunks sorted by relevance score, descending
    """

# Unit test for every module before moving to next
# File: tests/unit/test_reranker.py

# No hardcoded credentials
pinecone_key = os.environ["PINECONE_API_KEY"]  # correct
pinecone_key = "pc-abc123"  # never do this

# All AWS resource names prefixed with finrag-
bucket_name = "finrag-raw-filings"  # correct
bucket_name = "my-bucket"  # wrong
```

---

## Phase 9: Key Constraints

Every answer generated by this system must satisfy all of these:

1. Every number in the answer MUST appear verbatim in a retrieved chunk
   (numerical_verifier.py enforces this before response is returned)

2. Every answer MUST include inline citations in format:
   [NVDA 10-Q Q1-2026 p.23]

3. If retrieval confidence is low or context is insufficient:
   The system MUST refuse to answer rather than hallucinate
   Response: "I could not find reliable data for this question in the ingested filings."

4. All query costs MUST be logged to DynamoDB with breakdown per stage

5. CI eval must pass before any PR is merged:
   faithfulness >= 0.85 and numerical_accuracy >= 0.90

6. Never merge a change that drops any ragas metric by more than 0.05

---

## Phase 10: Cost Budget

| Service | Monthly Cost |
|---|---|
| BeautifulSoup4 + lxml + pandas | $0 |
| Pinecone free tier | $0 |
| rank-bm25 in-memory | $0 |
| CrossEncoder HuggingFace | $0 |
| Bedrock free tier (first 3 months) | $0 |
| S3 storage | ~$3 |
| DynamoDB | $0 (free tier) |
| Lambda + API Gateway | $0 (free tier) |
| CloudWatch | ~$2 |
| Cognito | $0 |
| Vercel | $0 |
| GitHub Actions | $0 (public repo) |
| **Total** | **~$5/month** |

Set AWS Budget alert at $20/month as a safety net.
If any service approaches $10, stop and investigate before continuing.

---

## Phase 11: Current State (Update Every Session)

```
Current week: 3 DONE, 5 (deployment) IN PROGRESS -- Lambda live with all 4
  MCP tools; Cognito + weekly refresh still open
Branch: week5-deployment (pushed to origin, not yet merged), off main which
  has week3-eval-harness merged (PRs #3/#4)
Test status: 203 unit tests passing, ruff clean

DEPLOYED: finrag-mcp-server Lambda + Function URL, us-east-1, arm64,
  2048MB/120s/2GB ephemeral. Bearer auth checked before any cold-start work.
  Secrets via SSM /finrag/* (openai-api-key, pinecone-api-key,
  mcp-auth-token). Verified live: canonical FinanceBench Q1 (3M FY2018
  capex) returns $(1,577)M cited to MMM 10-K 2019-02-07, matching local.
  Claude Desktop config written (~/Library/Application Support/Claude/
  claude_desktop_config.json, backed up to .bak first).

All 4 MCP tools built (TDD) and live: search_sec_filings,
  get_company_financials, compare_companies, get_latest_filing. Tools 2/3
  deliberately skip the Haiku rewrite call (input is already structured --
  ticker/metric/period, nothing to expand from natural language) and go
  straight to GAAP-expansion + hybrid search + rerank + verify. Tool 4 skips
  the RAG pipeline entirely: metadata comes live from EDGAR (corpus can lag
  it by up to a week), summary is one Haiku call over whatever's ingested,
  with the same Bedrock->OpenAI fallback every other LLM call site has.
  Live testing caught and fixed a real bug before it shipped: compare_
  companies(["TSLA","F"], revenue, 2024) cited Ford's number to a *Pfizer*
  10-K -- "F" was too weak a lexical token to constrain BM25/dense retrieval
  to Ford alone. Fixed by filtering candidates to the requested ticker
  (metadata we already have) before reranking, since -- unlike
  search_sec_filings' free-text queries -- the ticker is a known input for
  these two tools. Re-verified live after the fix: TSLA answered correctly,
  F correctly refused ("context does not provide") instead of misattributing.
  Old bm25/index.pkl deleted from S3 (was superseded by FTS5, sat unused).

rank-bm25 replaced with SQLite FTS5 (server/*, pipeline/sync_pinecone.py
  KeywordIndex): old in-memory build peaked at 7.5GB and needed a temporary
  EC2 box; FTS5 streams in bounded memory (568MB peak) and serves from disk.
  Also fixed real bm25/index.pkl bugs found only once this ran on Lambda:
  server embedded queries with Titan while the corpus is OpenAI-embedded
  (get_embed_fn() now shared between server and eval harness); DNS-rebinding
  host check rejected every Function URL request (421); MCP session
  manager's run-once-per-instance broke warm Lambda invocations.
Corpus: 71/72 companies ingested. FY2018-2026 depth for the 32 FinanceBench
  companies, 2025-2026 for the other 40. SPOT out of scope (20-F filer, not
  10-K/10-Q). PYPL temporarily absent (Pinecone free-tier write cap hit
  mid-project; resets monthly; costs 1 FinanceBench question).

Eval scores (FINAL, real, 150/150 answered + 600/600 ragas calls scored,
deterministic pipeline, evals/results/eval_1790044494.json):
  numerical_accuracy   0.910   (our own verifier, not LLM-judged)
  faithfulness          0.801
  answer_relevancy       0.156   -- see caveat below
  context_precision      0.200   -- see caveat below
  context_recall          0.113   -- see caveat below

Caveat, not yet resolved: the three low ragas metrics held steady across
every complete run today regardless of the fixes below, including after
directly verifying (Q1, 3M FY2018 capex) that retrieval finds the exact
correct chunk and number. Working theory: ragas's LLM-judged relevancy/
precision/recall metrics fit narrative QA poorly against terse numeric
ground truths ("$1577.00") scored against pipe-delimited table chunks.
Stated as an open question in README.md, not claimed as solved.
```

### Why the corpus is being rebuilt (the bug that invalidated the first eval)

The first eval returned faithfulness 0.96 but ~0.0 on every context metric.
Four independent defects, each invisible because the pipeline still returned
fluent, plausible answers:

1. `merge_and_dedup` concatenated BM25-then-dense and `rerank` truncated with
   `chunks[:top_k]`, so the top-5 was always 100% BM25 -- every dense result
   was discarded. Hybrid search was keyword-only.
2. `search_filings` built citations without the chunk `text` the harness reads
   as ragas `contexts`, so context metrics scored against empty strings.
3. `numerical_verifier` used a substring test: "$1,234" matches "$1,234.56",
   so fabricated figures passed the grounding check.
4. `chunk_id` was `uuid4()`, so re-ingest duplicated every chunk and BM25 ids
   never matched Pinecone ids -- cross-source dedup could not work.

Then the root cause underneath all of it: `list_filings` defaulted to the last
2 10-Ks and 4 10-Qs, which in 2026 means 2025-2026 filings, while FinanceBench
asks about 2015-2024. The corpus held the right companies for the wrong years,
so 147 of 150 questions were unanswerable and the model correctly said the
context did not contain the figure. Benchmark companies now ingest
{10-K: 8, 10-Q: 12, 8-K: 8} -- 28 filings each instead of 6.

After the corpus rebuild, the first full eval run still returned near-zero
on three ragas metrics for reasons that turned out to be pipeline bugs, not
just the metric-fit question above:

5. Query vs. filing vocabulary gap: "capital expenditure" appears nowhere in
   a cash flow statement -- the line reads "Purchases of property, plant and
   equipment (PP&E)". Zero term overlap meant BM25 and dense search both
   missed the one chunk holding the answer. Fixed with GAAP_SYNONYMS, a
   deterministic expansion appended after the LLM rewrite
   (query_rewriter.py).
6. The lexical reranker fallback (CrossEncoder deadlocks on macOS + Python
   3.13) scored by raw term-overlap fraction, which rewards length: an
   irrelevant LIBOR passage outscored the correct cash-flow table 0.769 to
   0.423 purely by accumulating more generic word matches. Fixed with
   candidate-set IDF weighting + BM25-style length normalization
   (reranker.py).
7. The generation prompt forbade the model from equating a GAAP line item
   with the analyst's term for it, so it refused to report a figure it had
   already found. Fixed by teaching the equivalence and the accounting sign
   convention explicitly (answer_generator.py).
8. **No temperature was pinned anywhere.** The same question through the
   identical fixed pipeline produced a correct cited answer once and "the
   context does not provide this figure" once -- a coin flip at each API's
   default temperature (1.0). All four LLM call sites (Bedrock + OpenAI
   fallback, rewriter + generator) now pin temperature=0.
9. Four separate gaps where a transient network fault crashed the whole
   150-question run instead of retrying or falling back: Bedrock timeouts
   weren't recognized as "unavailable" (text-only match, not exception
   type), the OpenAI fallback's own retry loop only caught rate-limit text,
   query_rewriter's OpenAI path had no retry at all, and loading the ~1GB
   BM25 pickle from S3 had no retry on a mid-stream read timeout. All four
   now retry by exception type, matching the pattern EDGAR retries already
   used.

Operational lessons now enforced in code, not memory:
- EDGAR and S3 requests retry connection/timeout faults by exception type,
  not by matching error text (text matching missed real fault classes twice)
- A partial run refuses to publish BM25; doing so once overwrote a 71-company
  index in S3 with a 42-company one, leaving the corpus worse than before
- Guard test fails if BENCHMARK_TICKERS drifts from the dataset
- Run with `caffeinate -dimsu`; laptop sleep has killed several runs
- Checkpointing per question means a mid-run crash costs zero re-spend --
  this held true through five separate crashes on the final eval run

### Priority order (deployment before observability)

Rationale: nothing is deployed yet, so resume bullet 3 ("Deployed AWS
serverless... Cognito... CloudWatch") has nothing behind it. A live demo is
worth more at a career fair than cost metrics, and Lambda also re-enables the
real CrossEncoder reranker (torch deadlocks on macOS + Python 3.13, so it
currently falls back to a lexical scorer locally).

```
DONE -- Week 3 (merged to main via PR #3/#4)

DONE so far -- Week 5 deployment
  [x] rank-bm25 -> SQLite FTS5 (KeywordIndex): 7.5GB build -> 568MB, no EC2
  [x] Fixed server's Titan/OpenAI embedder mismatch (get_embed_fn() shared)
  [x] infra/stacks/mcp_server_stack.py -- Lambda + Function URL, no Docker
      (local pip bundling), no API Gateway (29s cap too short for cold start)
  [x] Fixed 3 bugs only visible once actually deployed: DNS-rebinding host
      check (421 on every request), session-manager run-once-per-instance
      (crashed warm invocations), unauthenticated requests triggering full
      cold starts before the 401
  [x] Bearer auth (interim until Cognito), SSM secrets, scoped IAM
  [x] Deployed. Live-tested: canonical FinanceBench Q1 matches local exactly
  [x] Claude Desktop config written (backed up original first)
  [x] README.md Deployment section; this section updated
  [x] S3 cleanup: deleted unused bm25/index.pkl
  [x] get_company_financials, compare_companies, get_latest_filing -- all 3
      built TDD, deployed, live-verified; 1 real bug found live and fixed
      (cross-ticker citation on single-letter tickers -- see above)
  [ ] Push week5-deployment, open PR to main  <-- do this next
  [ ] Manually verify in Claude Desktop (restart app, ask a real question)

  Rerun commands (for future reference):
    python3 scripts/bootstrap_corpus.py          # skips cached tickers
    PYTHONPATH=. python3 evals/run_eval.py       # checkpoints per question
    PYTHONPATH=. npx -y aws-cdk deploy FinragMcpServerStack --app "python3 infra/app.py" --require-approval never

DONE -- Cognito OAuth 2.1/PKCE (dual-accept, not yet a hard cutover)
  [x] server/auth/cognito_validator.py -- JWKS signature, issuer, client_id,
      token_use, scope, all TDD (8 tests, real RSA keypair, no live Cognito
      needed to test the logic)
  [x] CDK: single-user Cognito pool (no self-signup), public PKCE app
      client (no secret), finrag/invoke resource-server scope, hosted domain
  [x] server/main.py: _is_authorized accepts EITHER the static token or a
      valid Cognito JWT -- deliberately not a cutover, see below
  [x] /.well-known/oauth-protected-resource (RFC 9728) so a client's OAuth
      discovery can actually find Cognito -- without this, wiring the
      validator alone is unreachable dead code. Bug caught live: the
      FastAPI-level auth bypass for this path never ran, because
      handler()'s OWN earlier auth check (checked before create_app() is
      even built, by design, to avoid a cold start on anonymous probes)
      rejected it first. Fixed with a matching bypass at that layer too.
  [x] Deployed. Live-verified: discovery endpoint public (200, no token),
      static bearer token still works unchanged (regression-checked after
      every one of the 3 deploys above)
  [x] Cognito user created (admin-create-user, FORCE_CHANGE_PASSWORD --
      sets their own password on first hosted-UI login, not set by Claude)
  [x] Three real bugs found by actually attempting the login flow (not
      just deploying and assuming): (1) mcp-remote defaults to OAuth
      Dynamic Client Registration, which Cognito doesn't support -- fixed
      client-side with --static-oauth-client-info pointing at the
      pre-registered app client; (2) Cognito's hosted UI failed with a
      bare unexplained error -- mcp-remote derives its local callback port
      from a hash of the server URL (11164 for this Function URL), not a
      fixed default, and the CDK-registered callback URL had a guessed,
      wrong port (8090); (3) invalid_scope -- the app client only allowed
      the custom finrag/invoke scope, but mcp-remote's default authorize
      request always includes openid/email/phone/profile too, and Cognito
      rejects the whole request if any requested scope isn't allowed.
      See README's Deployment section for the working config + full
      writeup.
  [x] CLI-verified after both infra fixes: the authorize URL now returns
      302 (real login redirect), not an OAuth error
  [x] VERIFIED END TO END (2026-09-24): Claude Desktop -> mcp-remote ->
      Cognito login -> tool call on the Lambda with a Cognito token, no
      static header. Needed two more client-side flags beyond the static
      client id: scope "openid finrag/invoke" (Cognito's discovery never
      lists custom scopes, so mcp-remote otherwise omits it -> 401) and
      token_endpoint_auth_method "none" (public PKCE client). Desktop reads
      its config only at launch -- a stale running app caused one round of
      false failures.
  [x] Retire the static MCP_AUTH_TOKEN bearer path -- DONE 2026-09-24, see A3

RETRIEVAL BUG FOUND IN LIVE USE (2026-09-24) -- FIXED same day (A1)
  Natural phrasings ("3M capital expenditure FY2018") return "context does
  not provide"; only the verbose FinanceBench wording (mentions "cash flow
  statement") finds the FY2018 10-K. Cause: all 28 MMM filings contain
  near-identical PP&E cash-flow rows, and nothing ties "FY2018" to the 10-K
  filed 2019-02-07, so 2022-2023 look-alikes crowd it out of top-k.
  Proposed fix: time-aware retrieval -- rewriter extracts ticker + fiscal
  year, passed as metadata filters to Pinecone and the FTS5 index. Then
  re-run the 150Q eval to confirm no regression.
  Outputs: CognitoUserPoolId us-east-1_DfcfEbPLO, CognitoClientId
    5n9n0e2ugjnklckjlrtc50p9c4, CognitoAuthorizeUrl
    https://finrag-mcp-496158977343.auth.us-east-1.amazoncognito.com

DONE -- EventBridge weekly refresh
  [x] scripts/weekly_refresh.py -- diffs EDGAR's current filing list against
      the cache (by filing_date) and ingests only what's new, instead of
      bootstrap_corpus.py's "cached ticker = skip forever" (wrong for a
      recurring job) or blindly re-ingesting everything (would re-embed and
      re-upsert 2000+ unchanged filings weekly, burning OpenAI spend and
      re-tripping the Pinecone write cap that already cost a FinanceBench
      question). All-or-nothing per ticker, same discipline as bootstrap.
  [x] Persisted the chunk cache to S3 (chunk_cache/ prefix in
      finrag-processed-filings) -- caught before deploying: a weekly Lambda
      is guaranteed a cold start every invocation, so local /tmp starts
      empty every time. Without syncing to S3, the diff logic would see
      zero cache and re-ingest the whole corpus every week regardless.
  [x] infra/stacks/ingestion_stack.py -- second Lambda (pandas/lxml/bs4/
      tiktoken the MCP server excludes to stay small; fits at 221MB under
      the 250MB zip limit, same no-Docker local-pip-bundling as the server),
      EventBridge rule at rate(7 days), 15-min timeout (Lambda's max, not a
      margin -- a big filing week could still exceed it; safe no-op if so,
      next week's run picks up where it left off), IAM scoped to exactly
      the S3 prefixes/objects it touches
  [x] Deployed (FinragIngestionStack). Seeded S3 chunk_cache/ from the
      local corpus's 71 existing cache files -- without this one-time
      seed, the FIRST scheduled run would still see an empty S3 cache and
      re-ingest everything once before settling into normal diff behavior
  [ ] Not live-tested: invoking it would cost real OpenAI/Pinecone spend
      across 71 tickers just to verify "up to date" logging. Correctness
      verified via 14 unit tests (diff logic, S3 sync, failure handling,
      partial-run safety) instead of a live run

=====================================================================
SESSION HANDOFF (updated 2026-09-25) -- read this first in a new chat
=====================================================================
Where we are: Phase A (all), Phase B (all), C1, C2 DONE. NEXT = C3
  (Bedrock prompt caching on the generation system prompt). Work the
  MASTER CHECKLIST below strictly one item at a time; explain in plain
  language, stop after each item for the user's go-ahead.
Branch: main (week5-deployment merged 2026-09-24). All work today
  committed directly to main, pushed after every item. Last commit:
  cb5ea36 "docs: C1 done and live-verified".

What shipped today (2026-09-25), in order:
  - A2: 30Q CI regression after A1 -- no regression, numerical_accuracy
    actually improved 0.910->0.949
  - A3: retired the static bearer token, Cognito-only auth now. Real bug
    caught+fixed: _is_authorized silently accepted a header missing the
    "Bearer " prefix
  - A5: week5-deployment merged to main (rebase-merge PR)
  - Phase B: dense_only/bm25_only baseline modes added to
    build_search_filings_answer(); Baseline A/B run 150Q each; comparison
    table in README. Real bug caught+fixed: an oversized table chunk (no
    dense/rerank pass in BM25-only to screen it out) blew Sonnet's context
    window -- fixed with MAX_CHUNK_CHARS cap in generate_answer()
  - C1: real cost_usd + per-stage latency + DynamoDB logging, wired into
    all 3 relevant tools, live-verified on the deployed Lambda
  - C2: baseline cost/latency measured on 15 real FinanceBench questions
    pre-caching/routing: avg cost_usd 0.013677, avg latency_ms 24109 --
    this is the "before" number C6 compares against after C3-C5

Live-test the deployed server (Cognito-only; static token retired in A3,
gets 401). A real Cognito access token needs the hosted-UI login flow
(through Claude Desktop / mcp-remote, or manually) -- there is no static
header to source anymore:
  caffeinate -i curl -sS -X POST "https://ecvsxkeqdpyj5hkal7wplm2b4q0gacfh.lambda-url.us-east-1.on.aws/mcp" \
    -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
    -H "Authorization: Bearer <cognito-access-token>" --max-time 110 \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_sec_filings","arguments":{"query":"3M capital expenditure FY2018"}}}'
  Expected: $(1,577) million cited to [MMM 10-K 2019-02-07].

To live-verify a change WITHOUT a Cognito token (what today's C1/C2 work
actually used) -- calls real Bedrock/Pinecone/DynamoDB directly, bypassing
HTTP/auth entirely, same production dependency-building code the Lambda
runs:
  export OPENAI_API_KEY=$(aws ssm get-parameter --name /finrag/openai-api-key --with-decryption --region us-east-1 --query Parameter.Value --output text)
  export PINECONE_API_KEY=$(aws ssm get-parameter --name /finrag/pinecone-api-key --with-decryption --region us-east-1 --query Parameter.Value --output text)
  PYTHONPATH=. OPENAI_API_KEY="$OPENAI_API_KEY" PINECONE_API_KEY="$PINECONE_API_KEY" python3 -c "
  import server.main as main
  deps = main._build_production_dependencies()
  bedrock, pinecone_index, keyword_index, embed_fn, dynamodb = deps
  from server.mcp_tools.search_filings import build_search_filings_answer
  r = build_search_filings_answer('<question>', bedrock, pinecone_index, keyword_index, embed_fn, dynamodb_resource=dynamodb)
  print(r['cost_usd'], r['latency_ms'], r['answer'][:200])
  "
  # ALWAYS follow with: rm -f /tmp/finrag/keyword.sqlite -- see disk gotcha below.

Deploy: PYTHONPATH=. npx --yes aws-cdk deploy FinragMcpServerStack \
          --app "python3 infra/app.py" --require-approval never
        then `rm -rf cdk.out`. Deploys take 1-2 min; run in background.
Logs:   aws logs tail FinragMcpServerStack-McpServerLogs06388123-18nUK8h9Qyv0 --since 30m
        Claude Desktop side: ~/Library/Logs/Claude/mcp-server-finrag.log
Query logs: aws dynamodb scan --table-name finrag-query-logs --region us-east-1

DISK IS CHRONICALLY NEAR-FULL ON THIS MACHINE -- not a one-time event, it
recurred twice today (once hitting genuine 0 bytes free, which blocks even
Bash's own output-file writes -- every tool call fails until freed). Root
cause: `load_keyword_index()` re-downloads the ~900MB keyword index to
local `/tmp/finrag/keyword.sqlite` every time it's called outside Lambda
(any eval run, any direct-pipeline verification script). Before ANY eval
run or direct-pipeline verification:
  df -h /   # if under ~1GB free, clean first:
  rm -rf "$(pwd)/cdk.out" ~/Library/Caches/pip evals/results/keyword_index.sqlite
And immediately after any script that calls _build_production_dependencies()
or load_keyword_index() directly (not through run_eval.py, which uses its
own S3-cached copy under evals/results/):
  rm -f /tmp/finrag/keyword.sqlite
This is a recurring tax, not fixed at the root. A real fix (e.g. stream
from S3 instead of caching locally for one-off scripts, or the user
permanently freeing disk elsewhere) is still open -- raise it if it bites
a third time.

Gotchas learned the hard way:
- The Mac sleeps mid-request: always wrap long runs in `caffeinate -i`
  (curl reported ~17-minute "timeouts" that were really sleep).
- Claude Desktop reads claude_desktop_config.json ONLY at launch -- after
  editing, Cmd+Q and reopen, or it silently keeps the old config.
- mcp-remote caches OAuth state in ~/.mcp-auth/mcp-remote-v1/; a stale
  cache made it ignore fixed flags. rm -rf it when auth acts strangely.
- Cognito login password: ~/.finrag/cognito-password.txt (user reads it
  themselves; never print it -- the credential classifier blocks that).
- Never add Co-Authored-By: Claude trailers to commits (user rule).
- Bedrock daily token quota can be exhausted after heavy runs; every LLM
  call site falls back to OpenAI gpt-4o-mini automatically.
- Neither AWS Cost Explorer (this IAM identity isn't enabled for it) nor
  the OpenAI API key in SSM (lacks the api.usage.read scope) can report
  real dollar spend programmatically. The user checks
  platform.openai.com/usage and the AWS Billing console directly for
  actual cost; cost_usd in DynamoDB/eval results is our own estimate, not
  a substitute for those.

=====================================================================
MASTER CHECKLIST (2026-09-24) -- do in this order, one item at a time.
Each item: TDD, deploy if it touches the server, verify live, update
this file + README, commit, push. "Done when" is the bar, not "code
written".
=====================================================================

PHASE A -- Make the demo reliable (do first)
  [x] A1. Time-aware retrieval fix (the 3M FY2018 bug above) -- DONE 2026-09-24:
          both failing phrasings now return $(1,577)M, all 5 citations
          from [MMM 10-K 2019-02-07], live on the deployed Lambda
          - rewriter extracts ticker + fiscal year from the question
          - pass as metadata filters to Pinecone + FTS5 keyword index
          - FY N annual figures -> 10-K filed in early N+1
          Done when: "3M capital expenditure FY2018" and "What was 3M's
          capex in fiscal year 2018?" both return $1,577M cited to
          [MMM 10-K 2019-02-07], on the deployed Lambda
  [x] A2. Regression check after A1: 30Q CI subset (run_ci_eval.py) -- DONE
          2026-09-24: numerical_accuracy 0.949 (up from 0.910 baseline),
          faithfulness 0.796 (flat vs. 0.801 baseline, both under the 0.85
          gate -- pre-existing, not caused by A1), context metrics all up.
          No regression from A1. Results: evals/results/ci_latest.json
  [x] A3. Retire the static bearer token (Cognito is now the only login) --
          DONE 2026-09-24:
          - dropped MCP_AUTH_TOKEN path from server/main.py + its tests
            (create_app/handler no longer take/require auth_token)
          - deleted /finrag/mcp-auth-token SSM param + ~/.finrag/mcp-headers.txt
          - real bug caught in the same pass: _is_authorized used
            `.removeprefix("Bearer ")`, which is a no-op (not a rejection)
            on a header missing that prefix -- a bare JWT without the
            scheme would have validated. Now requires the literal "Bearer "
            prefix before attempting Cognito validation.
          - live-verified on the deployed Lambda: old-style token -> 401,
            /.well-known/oauth-protected-resource still public (200)
          - deploy hit a real blocker: local disk was at 99% full (198MB
            free), which is why the pip bundling step failed with ENOSPC
            (the documented gotcha). Freed ~1GB by deleting cdk.out,
            the pip cache, and the local keyword_index.sqlite eval cache
            (reproducible, re-downloads from S3), then redeployed clean.
          Not yet done: a real Claude Desktop restart + Cognito browser
          login against this deploy (non-interactive session can't drive
          the hosted-UI consent screen) -- ask the user to confirm.
  [ ] A4. (USER) Rotate the OpenAI key pasted in chat; update SSM
          /finrag/openai-api-key. Done when: old key revoked on
          platform.openai.com, live query still answers
  [x] A5. (USER) Merge week5-deployment -> main via GitHub PR -- DONE
          2026-09-24: rebase-merged. main and week5-deployment content
          verified identical (git diff main week5-deployment: empty).
          main now at db4c3dd, all 35 Week 5 commits present.

PHASE B -- Prove the design choices (strongest interview material) -- DONE
  2026-09-24
  [x] B1. Baseline A: dense (Pinecone) only, no rewrite, no rerank -- 150Q.
          numerical_accuracy 86.5%, faithfulness 79.4%.
          evals/results/eval_dense_only_1790314408.json
  [x] B2. Baseline B: keyword (FTS5) only, no rewrite, no rerank -- 150Q.
          numerical_accuracy 94.4%, faithfulness 83.8%.
          evals/results/eval_bm25_only_1790318145.json
          Live bug caught and fixed mid-run: BM25-only has no dense/rerank
          pass to screen an oversized match, and chunker.py exempts table
          chunks from its size target -- a huge table chunk blew Sonnet's
          context window (ValidationException) at Q91/150. Fixed in
          generate_answer() (MAX_CHUNK_CHARS cap, server/generation/
          answer_generator.py), not per-mode, then resumed from checkpoint.
  [x] B3. Comparison table in README: Baseline A vs B vs full pipeline --
          DONE, "Baseline comparison" section under Eval results.
          Honest finding, not spun: BM25-only actually scored *higher*
          than the full pipeline on this benchmark (FinanceBench's
          questions are largely keyword-friendly). What the full pipeline
          demonstrably buys is the gap over dense-only search (+4.5pt
          numerical accuracy, +2.9pt context recall) -- hybrid retrieval
          and rewriting help most where dense embeddings alone miss a
          jargon-heavy financial term. Stated as an open finding in README,
          not resolved in the pipeline's favor by fiat.

PHASE C -- Cost & observability (Week 4, deferred until now)
  [x] C1. server/observability/logger.py -- per-query record to DynamoDB --
          DONE 2026-09-25, live-verified on the deployed Lambda:
          - estimate_cost_usd(): text-length-based token estimate (~4
            chars/token), documented as approximate -- exact usage would
            need threading a new return value through rewrite_query()/
            generate_answer() and every existing call site (all unit
            tests, run_eval.py, run_ci_eval.py, the CI gate)
          - log_query(): best-effort DynamoDB write to finrag-query-logs,
            never raises (a logging outage must not fail the user's query)
          - search_filings.py replaces cost_usd=0.0 with real cost, tracks
            per-stage latency (rewrite/retrieve/rerank/generate/verify)
          - get_financials.py cost_usd fixed; compare_companies.py sums
            each successful per-ticker hop's cost
          - server/main.py builds a boto3 dynamodb resource and threads it
            through create_app() -> register_search_filings_tool()
          - infra: dynamodb:PutItem IAM grant, scoped to the
            finrag-query-logs table ARN only
          - Live-verified end to end: ran one real query against the
            deployed Lambda's production dependencies (3M FY2018 capex),
            got cost_usd=0.007224 (not the old 0.0 stub), confirmed the
            row landed in DynamoDB via `aws dynamodb scan`
          Deploy hit disk full (0 bytes free, mid-session) -- see "Known
          gaps" below; the recurring cause is load_keyword_index()
          re-downloading the ~900MB index to /tmp locally whenever this
          verification script runs outside Lambda. Freed and cleaned up
          each time; not yet fixed at the root.
  [x] C2. Measure BASELINE cost/latency per query (before C3-C5), from
          C1's logs over a fixed question set -- DONE 2026-09-25, no
          caching/routing applied yet, so this is the true "before" number
          C6 compares against later:
          Fixed set: first 15 FinanceBench questions (evals/eval_data/
          financebench_150.json[:15]), run individually against real
          production dependencies (not mocked), logged to DynamoDB.
            avg cost_usd:     0.013677  (min 0.005593, max 0.032660)
            avg latency_ms:   24109     (min 15441,    max 36648)
            projected cost per 1,000 queries: ~$13.68
          16 rows confirmed in finrag-query-logs via `aws dynamodb scan
          --select COUNT` (15 + the earlier C1 live-verification query).
          Caveat carried from C1: cost_usd is the text-length token
          estimate, not exact provider usage -- directionally right for
          before/after comparison, not a billing-accurate number.
  [ ] C3. Bedrock prompt caching on the generation system prompt
  [ ] C4. Query result cache in DynamoDB (hash of normalized query)
  [ ] C5. Model tier routing: single-metric lookups -> Haiku,
          comparisons / multi-hop -> Sonnet
  [ ] C6. Re-measure cost/latency after C3-C5; before/after table in
          README; fill the cost numbers into Phase 14 resume bullets
  [ ] C7. CloudWatch dashboard (observability_stack.py): invocations,
          errors, latency, cost

PHASE D -- Corpus & eval completeness
  [ ] D1. Backfill PYPL (Pinecone monthly write cap has reset)
          Done when: PYPL chunks in Pinecone + FTS5, weekly refresh sees it
  [ ] D2. custom_150.json: replace VERIFY_AFTER_BOOTSTRAP placeholders
          with verified ground truths (needs USER review of answers)
  [ ] D3. Full 300Q eval (FinanceBench 150 + custom 150), README updated

PHASE E -- Public dashboard
  [ ] E1. dashboard/ Next.js + Recharts: EvalScoreChart,
          CostPerQueryChart, LatencyBreakdown, reading exported results
  [ ] E2. Deploy to Vercel, link from README

PHASE F -- Launch & polish (Week 6)
  [ ] F1. Final README pass: architecture diagram, setup, results, costs
  [ ] F2. Update all diagrams (query-sequence.mmd still shows 1 tool,
          no Cognito, no time filters)
  [ ] F3. Phase 14: switch to the "Final version" resume bullets, every
          claim backed by something live
  [ ] F4. (USER) 3-minute demo video: Claude Desktop answering with citations
  [ ] F5. Blog post: "What I learned building production RAG on AWS Bedrock"
  [ ] F6. Submit to the official MCP registry
  [ ] F7. (USER) Post on Hacker News (Show HN), r/LocalLLaMA, r/LangChain

DEFERRED -- revisit only if a reason appears
  [~] CrossEncoder reranker -- needs a container-image Lambda (Docker not
      installed locally); lexical fallback is live-verified at 91%
      numerical accuracy, CrossEncoder payoff unproven
  [~] Rate limiting -- plan assumed API Gateway; the Function URL has
      none, but the account's 10-concurrent-execution ceiling already
      caps traffic. Revisit if the account limit is ever raised
```

### Known gaps / debt

```
- custom_150.json ground truths are placeholders (VERIFY_AFTER_BOOTSTRAP);
  full eval currently scores FinanceBench 150 only, not the planned 300
- Three ragas metrics (answer_relevancy, context_precision, context_recall)
  score 11-20% despite verified-correct retrieval; likely a metric-fit issue
  for terse numeric QA over table-heavy context, not yet root-caused -- see
  README.md "Eval results" and Phase 11 caveat above
- PYPL missing from corpus: Pinecone free-tier monthly write-unit cap (2M)
  exhausted by repeated corpus rebuilds today. Resets monthly; backfill by
  deleting evals/results/chunk_cache/PYPL.json and re-running bootstrap
- CrossEncoder still disabled everywhere, including on the now-deployed
  Lambda (reranker.py's lexical fallback is what's live); needs a
  container-image Lambda (Docker not installed locally) -- deferred, see
  Phase 11 "NEXT" above for the reasoning
- infra/ has storage_stack.py and mcp_server_stack.py; pinecone_stack.py and
  observability_stack.py do not exist yet
- Cognito is deployed and wired (dual-accept), but not yet confirmed by an
  actual browser login -- the static bearer token is still the only path
  verified working end to end. Token lives in SSM and in Claude Desktop's
  local config file, not in any short-lived credential flow, until Cognito
  login is confirmed and the static path is retired
- get_company_financials/compare_companies filter retrieval candidates by
  exact ticker match on chunk metadata (fixes the Ford/Pfizer bug) but do
  not filter by period. Live test: querying MMM capex for FY2018 retrieved
  only 2023-2025 chunks and correctly refused rather than hallucinating --
  safe, but it won't find a period-specific answer that exists deeper in
  the corpus than hybrid_search's top_k=10 reaches. The full search tool
  handles this via Haiku's date-constraint extraction; tools 2/3 skip that
  call by design (see Phase 11 above), so they're weaker on ambiguous dates
- An OpenAI API key was pasted in plaintext in a chat session during setup
  this week and is considered exposed; rotate it in the OpenAI dashboard and
  update the /finrag/openai-api-key SSM parameter
```

---

## Phase 12: How to Start Each Claude Code Session

Paste this at the start of every new session:

"Read CLAUDE.md fully before responding.
We are on Week [X].
Last session I finished [Y].
Today I want to complete [Z].
Show me the current repo file structure before writing any code."

---

## Phase 13: Skills to Use

### ponytail (use on every coding task)
Invoke: start message with "ponytail:"
Effect: forces laziest working solution, no over-engineering
Use for: every implementation task

Example:
"ponytail: build edgar_client.py that downloads 10-Q filings
for 5 tickers into S3 using requests and boto3"

### superpowers/writing-plans (use before each week)
Invoke: "/writing-plans"
Effect: forces a detailed plan before any code is written
Use for: start of every new week

### superpowers/verification-before-completion (use after every module)
Invoke: "/verification-before-completion"
Effect: forces Claude to run the code and show real output before claiming it works
Use for: after every file is written

### superpowers/systematic-debugging (use when something breaks)
Invoke: "/systematic-debugging"
Effect: structured root cause analysis instead of random guessing
Use for: any error that does not resolve in 2 attempts

### caveman (use when you want fast output)
Invoke: "caveman mode:"
Effect: ultra-compressed responses, less explanation
Use for: when you already understand the context and just need the code

---

## Phase 14: Resume Bullets (Copy-Paste Ready)

### Current version (accurate as of this Week 3 close -- use this one now)

Verified against the actual codebase and eval results on this date. Every
claim below is either shipped and tested, or explicitly marked in-progress
-- nothing here should be indefensible if an interviewer asks to see it.

```
FinRAG MCP | Python, AWS Bedrock, MCP SDK, FastAPI, ragas    [In Progress]

• Built an EDGAR ingestion pipeline covering 71 companies and 2,000+ SEC
  filings (10-K/10-Q/8-K, up to 8 years of history per company) with
  table-aware HTML extraction, hierarchical chunking, and content-addressed
  chunk IDs for idempotent re-ingestion into Pinecone and a SQLite FTS5
  keyword index

• Engineered a four-stage retrieval pipeline — query rewriting (Claude Haiku
  plus a deterministic GAAP line-item expansion), parallel BM25/dense hybrid
  search, IDF-weighted reranking, and a custom numerical grounding verifier
  — achieving 91.0% numerical accuracy and 80.1% faithfulness on the
  150-question FinanceBench benchmark, with all 150 questions answered and
  independently spot-verified end to end

• Deployed serverless on AWS (Lambda behind a Function URL, arm64,
  SSM-managed secrets, scoped IAM); currently adding Cognito OAuth 2.1/PKCE
  and 3 additional MCP tools on top of the one already live
```

### Final version (DO NOT USE YET -- template for after Week 5 deployment)

Every claim here requires Lambda + API Gateway deployed, Cognito wired, and
a live endpoint to be true. Using this before that work is done would be a
bullet an interviewer could ask to see and find nothing behind. Fill in
cost-per-query numbers only after Week 4 observability produces them.

```
FinRAG MCP | Python, AWS Bedrock, MCP SDK, FastAPI, ragas               2026

• Built and deployed a production MCP server providing cited financial
  intelligence over 2,000+ SEC filings across 71 companies; automated the
  full EDGAR ingestion pipeline with table-aware document extraction,
  hierarchical chunking, and content-addressed chunk IDs for idempotent
  weekly refresh via EventBridge

• Engineered a four-stage retrieval pipeline — query rewriting (Claude Haiku
  plus deterministic GAAP line-item expansion), parallel BM25/dense hybrid
  search, IDF-weighted reranking, and a custom numerical grounding verifier
  — achieving 91.0% numerical accuracy and 80.1% faithfulness on the
  150-question FinanceBench benchmark

• Deployed serverless on AWS (Lambda, API Gateway) with Cognito OAuth
  2.1/PKCE; [cost per query numbers from Week 4]; ragas eval metrics wired
  into GitHub Actions CI with automated regression gates
```

---

## Phase 15: Interview Story

When asked "walk me through a project":

"I built FinRAG MCP, a production MCP server that plugs SEC financial intelligence
into any AI assistant. The problem is Claude and ChatGPT hallucinate financial numbers
because they are working from training data, not actual filings. My system downloads
real filings from EDGAR, processes them to handle tables properly, and exposes them
via MCP so any AI client can call my tools and get cited, accurate answers.

The retrieval stack is four stages: query rewriting with Haiku, parallel BM25 plus
dense search via Pinecone, CrossEncoder reranking, and a custom numerical grounding
verifier that checks every number in the answer actually exists in a retrieved chunk.

I measured everything against FinanceBench, a real benchmark with 300 labeled
financial questions. My pipeline hit [X]% faithfulness and [Y]% numerical accuracy
versus [Z]% for naive vector search alone. Cost per query dropped from $0.035 to
$0.011 after caching and model tier routing. All metrics are live on a public dashboard.

The thing I am most proud of is the numerical verifier. Financial RAG fails hardest
on numbers. The model confidently states a wrong revenue figure. Building a
post-generation check that catches ungrounded numbers before the answer reaches
the user was the hardest engineering problem in the project."

---

*This file is the single source of truth for this project.
Every Claude Code session starts by reading this file fully.
Every implementation decision must be consistent with this file.
If something in this file is wrong or outdated, fix it here first.*
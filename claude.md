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
Current week: 2 (code complete, push pending)
Last completed: all 8 automated Week 2 tasks -- query_rewriter, hybrid BM25+Pinecone,
  CrossEncoder reranker, numerical_verifier, answer_generator, wired into search_filings,
  50-company corpus expansion (bootstrap_corpus.py) + BM25 index built at end of bootstrap
Branch: week2-retrieval-quality (8 commits ahead of origin, push pending)
Next task: Task 9 (manual) -- deploy reranker container Lambda, run bootstrap_corpus.py
  against live AWS/Pinecone, then test 20 manual financial questions in Claude Desktop
Blockers: none (code complete; needs live AWS deploy to run Task 9)
Eval scores: not yet available (Week 3)
Latest ragas faithfulness: N/A
Latest numerical_accuracy: N/A
Cost per query: N/A
Test status: 32 unit tests passing; 3 tests skipped due to missing local deps
  (mangum, responses, aws_cdk -- pre-existing env issue, not regressions)
New diagram: diagrams/week2-query-sequence.mmd (full four-stage pipeline)
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

### Current version (in-progress, use while applying now)

```
FinRAG MCP | Python, AWS Bedrock, MCP SDK, FastAPI, ragas    [In Progress]

• Building a production MCP server for the Anthropic registry providing cited
  financial intelligence over 500+ SEC filings across 50 companies; automating
  the full EDGAR ingestion pipeline with table-aware document extraction,
  hierarchical chunking, and weekly data refresh via EventBridge

• Designing a four-stage retrieval pipeline — query rewriting (Claude Haiku),
  parallel BM25 and dense hybrid search via Bedrock KB, neural reranking, and a
  custom numerical grounding verifier to eliminate hallucinated financial figures —
  benchmarking against a 300-question FinanceBench dataset with ragas eval metrics
  wired into GitHub Actions CI with automated regression gates

• Deploying serverless on AWS (Lambda, API Gateway, DynamoDB, CloudWatch) with
  Cognito OAuth 2.1/PKCE and model tier routing; public Vercel dashboard tracking
  faithfulness, numerical accuracy, and cost per query in real time
```

### Final version (use after Week 3 when eval numbers are real)

Replace placeholders with real numbers after running FinanceBench eval.

```
FinRAG MCP | Python, AWS Bedrock, MCP SDK, FastAPI, ragas               2026

• Built and published a production MCP server to the Anthropic registry providing
  cited financial intelligence over 500+ SEC filings across 50 companies; automated
  the full EDGAR ingestion pipeline with table-aware document extraction,
  hierarchical chunking, and weekly data refresh via EventBridge

• Engineered a four-stage retrieval pipeline — query rewriting (Claude Haiku),
  parallel BM25 and dense hybrid search via Bedrock KB, neural reranking, and a
  custom numerical grounding verifier that eliminates hallucinated financial figures —
  achieving [X]% faithfulness and [Y]% numerical accuracy on a 300-question
  FinanceBench benchmark, a [Z]% improvement over baseline retrieval

• Deployed serverless on AWS (Lambda, API Gateway, DynamoDB, CloudWatch) with
  Cognito OAuth 2.1/PKCE; reduced cost per query from $0.035 to $0.011 via prompt
  caching and model tier routing; ragas eval metrics wired into GitHub Actions CI
  with automated regression gates and a public Vercel dashboard
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
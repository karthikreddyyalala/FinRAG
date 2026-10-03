# FinRAG MCP: interview prep

Everything you need to explain this project confidently, in the order you'd
actually need it. Simple version first, then technical, then the diagrams,
then the decisions and why you made them, then the questions people will
actually push on.

Last verified against the real code and eval files: 2026-10-03.

---

## Part 1: The simple version (for a recruiter, or the first 60 seconds)

**The problem.** If you ask ChatGPT or Claude "what was 3M's capital
expenditure in 2018?", you get one of three bad outcomes. It gives you a
number from training data that's months or years stale. It makes a number up
and states it with total confidence. Or it gives you something plausible with
nothing you can check it against. For anyone doing real financial work, all
three are useless, because the whole job is being right about numbers.

**The source of truth already exists.** Every public US company files
quarterly and annual reports with the SEC. Those filings are free, public,
and legally required to be accurate. The data is right there. The models just
aren't reading it.

**What I built.** A system that downloads those filings, makes them
searchable, and hands them to any AI assistant through a standard protocol
called MCP. So you ask Claude a financial question, Claude calls my server,
my server finds the exact passage in the exact filing, and the answer comes
back with a citation pointing at it.

**The part I care most about.** Before any answer reaches you, a separate
check pulls out every number in it and verifies that number actually appears
in the source text it claims to come from. If a number isn't there, it gets
stripped and replaced with "figure unavailable" rather than shown to you.
The system is built to say "I don't know" instead of guessing.

**One sentence version:** It's financial research that cites its sources and
refuses to make numbers up.

---

## Part 2: The technical flow

### What happens when someone asks a question

Walk through this in order. This is the `query-sequence.mmd` diagram.

**1. Auth.** The request hits an AWS Lambda behind a Function URL. A Cognito
JWT is validated (signature against JWKS, issuer, client ID, scope) before
*any* other work happens. That ordering is deliberate: an unauthenticated
request should cost nothing, and the first thing this Lambda does on a cold
start is download a ~900MB index.

**2. Cache check.** The query is normalized (lowercased, whitespace folded)
and hashed with SHA-256. If that hash is in DynamoDB and under 24 hours old,
return the cached answer and stop. A hit costs $0 and takes about 67ms versus
roughly 23 seconds for a miss.

**3. Extract filters.** Pull the ticker and fiscal year out of the question,
using *the user's own words*, not the LLM-rewritten version. The rewrite can
hallucinate company names and years that were never asked about, and you do
not want a hallucinated filter silently narrowing your search.

**4. Rewrite the query.** Claude Haiku expands tickers to company names and
pulls out time constraints. Then a deterministic GAAP synonym table appends
the filing's actual vocabulary. This matters more than it sounds: see
decision #7 below.

**5. Retrieve, two ways in parallel.**
   - Keyword search over a SQLite FTS5 index, BM25-ranked
   - Dense vector search over Pinecone, using OpenAI embeddings

   Both are filtered to the ticker and fiscal-year window from step 3. The
   two result sets are merged *interleaved by rank* (keyword #1, dense #1,
   keyword #2, dense #2...) and deduplicated by chunk ID.

**6. Rerank.** The merged pool of up to 20 candidates is rescored against the
*original* question (not the rewritten one) and cut to the top 5.

**7. Generate.** Claude Sonnet writes the answer from only those 5 chunks,
at temperature 0, with a system prompt requiring an inline citation on every
claim and an explicit refusal when the context doesn't contain the answer.

**8. Verify every number.** Extract every number from the generated answer.
Parse each into a numeric magnitude. Compare against the set of all numeric
magnitudes present in the source chunks. Anything that doesn't match gets
replaced inline with "[exact figure unavailable in retrieved context]".

**9. Log and cache.** Per-query cost and per-stage latency go to DynamoDB.
The answer goes into the 24h cache.

### How the corpus gets built

This is `ingestion-sequence.mmd`.

1. Resolve a ticker to its SEC CIK number (with a hardcoded override table
   for companies that were acquired or renamed, like SQ and ATVI, whose
   tickers no longer resolve)
2. Download the filings from EDGAR (free, public, no auth, 10 req/sec limit)
3. Parse the HTML with BeautifulSoup for text and pandas for tables, kept
   separate so table structure survives
4. Chunk hierarchically: sections at ~1500 words, paragraphs at ~400, and
   each table as its own chunk
5. Give each chunk a content-addressed ID: `sha256(ticker|form|period|type|section|text)`
6. Embed with OpenAI and upsert to Pinecone, batched by real token count
7. Rebuild the keyword index over the *whole* corpus, never just this run

A weekly EventBridge Lambda re-runs a diffed version of this: it asks EDGAR
what's filed now, compares against a cached list by filing date, and only
ingests genuinely new filings.

### The four MCP tools

| Tool | What it does | Why it's different |
|---|---|---|
| `search_sec_filings` | Free-text question, full pipeline | The main one |
| `get_company_financials` | ticker + metric + period lookup | Skips the LLM rewrite (input is already structured, nothing to expand) and routes to Haiku, since it's extracting one known number |
| `compare_companies` | Same metric across several tickers | Multi-hop: one lookup per company, then merged. Overrides back to Sonnet |
| `get_latest_filing` | Most recent filing + short summary | Skips the RAG pipeline entirely, metadata comes live from EDGAR |

### The numbers to have memorized

**Corpus:** 1,030 filings (506 10-Q, 284 10-K, 240 8-K), 164,092 chunks,
70 companies, up to 8 years of history.

**Accuracy, FinanceBench (150 public questions with verified answers):**
91.0% numerical accuracy, 79.4% faithfulness.

**Combined with 48 questions I hand-verified against filings:** 89.9%
numerical accuracy across 198 questions.

**Retrieval comparison, same 150 questions:**
- Dense (vector) only: 86.5%
- Keyword (BM25) only: 94.4%
- Full pipeline: 91.0%

**Cost and latency:** about $0.0137 and 24 seconds per query. Cache hit: $0
and 67ms.

**Tests:** 260 Python unit tests, 15 on the dashboard, CI green.

---

## Part 3: Which diagram to show, and when

There are four `.mmd` files. Do not show all four. Pick based on what they
asked.

### `diagrams/query-sequence.mmd` — your default
**Show this one for almost every question.** It's the per-query pipeline:
auth, cache, filters, rewrite, hybrid retrieval, rerank, generate, verify,
log. It also has notes embedded explaining three real bugs, which gives you
natural places to go deeper if they're interested.

Use it when they ask: how does it work, walk me through a request, where does
the LLM fit, how do you prevent hallucination.

### `diagrams/ingestion-sequence.mmd` — the data pipeline
Show this when they ask about data engineering, scale, how you got the
filings, how you keep it fresh, or what happens when a company files
something new. It covers both the one-time corpus build and the weekly
refresh cron.

### `diagrams/week3-eval-sequence.mmd` — the eval harness
Show this when they ask how you know it works, how you measure quality, or
about testing and CI. This is the one that separates you from people who
built a demo, so don't skip it if evaluation comes up.

### `diagrams/week1-sequence.mmd` — do not show
It's a deliberately preserved historical snapshot of the Week 1 architecture.
It's accurate for that point in time and wrong about the current system.
It exists to show evolution, not current state. If you show it by accident
you'll describe a system that no longer exists.

**Rendering note:** all four are Mermaid, verified to parse. The two main
ones are also embedded directly in the README so they render on GitHub
without anyone clicking into a file.

---

## Part 4: The decisions, and why

This is the section that matters most in a senior interview. Anyone can
describe what they built. Explaining *why*, including what you rejected, is
the signal.

### 1. Why MCP instead of building a chat app
A chat app means I own the UI, the auth, the conversation state, and I'm
competing with every other chat app. MCP is a protocol: I implement it once
and the tool works inside Claude Desktop, Cursor, or anything else that
speaks it. I built capability, not another interface. It also forced a
cleaner boundary: my server returns structured data with citations, it
doesn't own the conversation.

### 2. Why Pinecone instead of OpenSearch Serverless
OpenSearch Serverless bills around $100/month baseline even at zero queries.
Pinecone's free tier handles this corpus. For a personal project the
difference is the project existing or not. The tradeoff I accepted: a
free-tier write cap that I eventually hit, which is why one company (PayPal)
is still missing from the corpus. I'd rather say that out loud than pretend
the corpus is complete.

### 3. Why SQLite FTS5 instead of the obvious in-memory BM25 library
I started with `rank-bm25` in memory. Building that index peaked at **7.5GB
of RAM**, which didn't fit in Lambda and needed a temporary EC2 box just to
construct. SQLite FTS5 builds the same index streaming, in bounded memory
(568MB peak), and serves it from disk. This is a good story because it's a
real constraint I hit and engineered around, not a preference.

### 4. Why OpenAI embeddings instead of Bedrock Titan
Two reasons, both discovered rather than planned. Titan's output dimensions
didn't match the 1536-dimension Pinecone index I'd already built. And the
local ONNX alternative I tried was roughly 100x slower. The real lesson here
is a bug it caused: for a while the *server* was embedding queries with Titan
while the *corpus* was embedded with OpenAI. Those vectors aren't comparable,
so semantic search was quietly garbage. Now one shared `get_embed_fn()` is
used by both the server and the eval harness so they cannot drift.

### 5. Why Lambda Function URL instead of API Gateway
API Gateway caps integration timeouts at 29 seconds. A cold start here
includes downloading a ~900MB index, which blows straight through that. The
Function URL has no such cap. The cost: I lost API Gateway's built-in rate
limiting, which I've documented as a real gap rather than pretending it isn't
one. It's acceptable only because the account's concurrency ceiling is 10.

### 6. Why hybrid search instead of just vectors
Everyone reaches for vector search. On this benchmark, dense-only scored
86.5% and hybrid scored 91.0%. Financial language is full of exact tokens
(ticker symbols, line-item names, specific years) where keyword matching is
simply better, and embeddings alone miss them. **But be honest here**: plain
keyword search scored 94.4%, higher than my full pipeline. See the weak spots
section.

### 7. Why a hardcoded synonym table alongside an LLM rewrite
"Capital expenditure" appears nowhere in a cash flow statement. The line item
reads "Purchases of property, plant and equipment (PP&E)". Zero term overlap,
so BM25 had nothing to match on and the embedding wasn't reliably bridging it
either. I added a deterministic GAAP synonym table that runs *after* the LLM
rewrite. It's boring and hardcoded, and that's the point: unlike asking an
LLM to expand the query, it does the same thing every single time. Not
everything should be a model call.

### 8. Why the verifier compares numbers, not text
The first version checked whether the number appeared as a substring in the
sources. `"$1,234"` is a substring of `"$1,234.56"`, so a fabricated figure
passed the exact check designed to catch it. Now it parses both sides into
numeric magnitudes and compares values. Side benefit: financial tables write
negatives as `$ (1,577)` while a correct answer says `$1,577`, which share
almost no literal text but the same magnitude, so comparing values fixes both
problems at once.

### 9. Why content-addressed chunk IDs
They were `uuid4()`. That meant re-ingesting a filing created entirely new
IDs for identical content, so re-runs duplicated chunks, and the keyword index
IDs never matched the Pinecone IDs, which silently broke cross-source
deduplication. Now the ID is a SHA-256 of the content and its metadata, so
the same chunk always gets the same ID and re-ingest overwrites instead of
duplicating.

### 10. Why temperature is pinned to 0 everywhere
The same question through the identical pipeline returned a correct cited
answer once and a refusal the next time. Nothing had changed. No temperature
was pinned, so both the rewriter and the generator were running at the
provider default of 1.0. For a system whose job is factual retrieval,
sampling variance is pure downside, and it destroys your ability to tell
whether a change helped.

### 11. Why a 24-hour cache TTL specifically
The corpus refreshes weekly. A longer TTL saves more money but risks serving
an answer from before a company filed something new. 24 hours guarantees a
cached entry can never survive into a week where the corpus changed.

### 12. Why route single lookups to Haiku but comparisons to Sonnet
`get_company_financials` extracts one already-located number from a short
context. That doesn't need the strongest model. On a real spot-check both
models returned the identical correct answer, with Haiku at about a third of
the cost. `compare_companies` reasons across multiple companies, so it
overrides back to Sonnet.

### 13. Why I evaluated prompt caching and did NOT use it
This one is worth telling because the answer is "no". Bedrock requires at
least 1,024 tokens in the cached prefix; my system prompt is about 257. Under
the minimum, a cache point silently caches nothing. And a cache miss bills at
1.25x normal input price, so at low traffic it would cost *more* than not
caching. I did find and fix a real bug while investigating: the "stable"
system prompt was interpolating a per-query citation example, so it was never
byte-identical anyway.

### 14. Why Cognito OAuth instead of a simple API key
I started with a static bearer token as an interim. Once the real OAuth flow
worked end to end from Claude Desktop, I deleted the static path entirely
rather than leaving both. Keeping a weaker fallback alive next to a strong
one means you effectively have the weaker one. Fixing it also surfaced a real
bug: the auth check used `.removeprefix("Bearer ")`, which is a *no-op* on a
header missing that prefix rather than a rejection, so a bare token without
the scheme would have validated.

### 15. Why the eval harness is the actual centerpiece
Anyone can build a RAG demo that answers a few questions impressively. The
reason I can tell you hybrid beats dense-only by 4.5 points is that I built
the measurement before trusting the system. Nearly every real bug in this
project was found by a metric disagreeing with another metric, not by looking
at output.

---

## Part 5: The weak spots, and how to answer them

Do not hide these. Being the person who already knows their system's
limitations is a much stronger position than being caught by them.

### "Keyword search beat your pipeline. Why keep the complexity?"
This is the sharpest question and it's fair. Answer: on this benchmark, yes,
94.4% versus 91.0%. FinanceBench's questions are worded close to how filings
word things, which is near best case for lexical matching. What I can defend
with data is that the full pipeline beats dense-only by 4.5 points. What I
*can't* claim without measuring is that it would win on paraphrased or harder
questions, and I'm not going to claim it. I published the table that makes me
look worse because the alternative is believing my own architecture diagram.

### "Your faithfulness is only 79%."
True, and middling for production RAG where people target 85%+. It's the
number I'd attack next. Part of the gap is a metric-fit problem (see below),
but I haven't proven that, so I'm not going to use it as an excuse.

### "Three of your eval metrics are between 2 and 20%. Is retrieval broken?"
I don't think so, and I can show why: I manually verified for spot-checked
questions that retrieval finds the exact correct chunk and the exact correct
number. My working theory is metric fit, since ragas is judging terse numeric
ground truths like `"$1577.00"` against long pipe-delimited table chunks,
which is not the narrative QA shape those metrics were designed for. But I've
labelled it an open question rather than a solved one, because I haven't
traced it to a specific reproducible cause the way I did with other bugs.

### "Your own hand-verified question set scored *lower* than the public one."
Yes, 86.2% versus 91.0%, and I root-caused it rather than leaving it. Two
things. First, about half is a measurement artifact: my number-extraction
regex reads "Q4" as the number 4, so 11 honest refusals got docked for a
number the answer never claimed. Second, the rest is a real retrieval bug:
for "Q4 202X" phrasing, the pipeline sometimes retrieves the wrong fiscal
quarter's filing entirely. I confirmed it by reading the retrieved chunks.
Neither is fixed yet, and I can tell you exactly what the fix needs to be:
constrain the period filter by quarter, not just fiscal year, and
disambiguate segment subtotals from consolidated totals that share a line
label.

### "Can I use it?"
No, and that's deliberate. It's a single-user Cognito pool with no self-signup.
Opening it would put my personal AWS account, OpenAI key, and Pinecone free
tier behind a public endpoint with no rate limiting. The repo is set up so you
can deploy your own in about five steps. This is also why I decided *not* to
submit to the official MCP registry: their rules require a remote server to be
publicly accessible, and mine isn't, so listing it would be listing something
nobody can use.

### "Are you using a real reranker?"
Not currently. The plan was a CrossEncoder model, but torch deadlocks on macOS
with Python 3.13 during the first forward pass, and running it on Lambda needs
a container image I didn't build. The live system uses a lexical reranker with
IDF weighting and length normalization. I'll tell you honestly that the
CrossEncoder's payoff here is unproven, since the lexical version gets 91%.

### "Has the weekly refresh actually run in production?"
It's deployed, scheduled, and covered by 14 unit tests, but I've never
live-invoked it, because a real run costs actual OpenAI and Pinecone spend
across 70 tickers to verify "nothing changed" logging. I say "scheduled", not
"proven in production".

---

## Part 6: The three stories to have ready

Interviewers remember stories, not architecture. Have these three.

### The substring bug (your best one)
The component whose entire job was catching fabricated numbers was approving
them, because `"$1,234"` is a substring of `"$1,234.56"`. Nothing crashed. The
output looked perfect: a cited number and a verifier that said OK. It taught
me that when you write a component to prevent one specific failure, you have
to write the test that proves it prevents *that* failure. I had tests. None
tested the case the thing existed for.

### The silent hybrid search
My merge concatenated keyword results then dense results, and the reranker
truncated with `chunks[:5]`. Each is reasonable alone. Together they meant
every single vector search result fell off the end, so I was paying for
embeddings and discarding all of them. The system kept working because
keyword search is decent, so there was no visible symptom. What caught it was
two metrics disagreeing: faithfulness at 0.96 while every context metric sat
near zero. That combination is impossible, and chasing why is what found it.

### The right companies, the wrong years
An early eval came back with the model refusing nearly every question. My
instinct was that retrieval was broken. It wasn't. The ingestion defaulted to
"last 2 annual and 4 quarterly filings", which in 2026 means 2025-2026, while
the benchmark asks about 2015-2024. The corpus had exactly the right companies
and almost none of the right years. The model was behaving perfectly,
correctly refusing questions it had no data for. A serious bug and correct
behavior produced identical-looking output.

---

## Part 7: Quick self-test

If you can answer these without notes, you're ready.

1. Why does auth happen before anything else in the Lambda?
2. Why is the merge interleaved instead of concatenated?
3. Why does the reranker use the original query, not the rewritten one?
4. Why compare numeric magnitudes instead of strings?
5. Why is the fiscal-year filter extracted from the user's words and not the LLM rewrite?
6. What scored higher than your full pipeline, and why do you still defend the pipeline?
7. Why is the cache TTL 24 hours and not a week?
8. Why did you evaluate prompt caching and then not use it?
9. What's the difference between how `search_sec_filings` and `get_company_financials` work?
10. Name a bug you found through a metric rather than through an error.

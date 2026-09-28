// Stage descriptions sourced from diagrams/query-sequence.mmd and
// server/main.py / server/mcp_tools/search_filings.py's real call order.
export const PIPELINE_COPY = [
  {
    id: "auth",
    stage: "Cognito auth",
    technical: "A bearer token is validated against Cognito's JWKS before any cold-start work runs.",
    simple: "First, we check you're allowed to ask.",
  },
  {
    id: "cache",
    stage: "Cache check",
    technical: "The normalized query is hashed and checked against a 24h DynamoDB cache (search_sec_filings, full mode only).",
    simple: "If someone asked this exact question in the last day, we reuse that answer instantly.",
  },
  {
    id: "filters",
    stage: "Ticker + fiscal-year filters",
    technical: "The rewriter extracts a ticker and fiscal year, passed as metadata filters to Pinecone and the FTS5 index — this is what stops a 2018 answer being drowned out by near-identical 2022 filings.",
    simple: "We figure out which company and which year you actually mean.",
  },
  {
    id: "rewrite",
    stage: "Haiku rewrite + GAAP expansion",
    technical: "Claude Haiku expands the query, then a deterministic GAAP synonym table adds the filing's actual line-item wording (e.g. \"capital expenditure\" → \"purchases of property, plant and equipment\").",
    simple: "We translate your question into the exact words a filing uses.",
  },
  {
    id: "retrieve",
    stage: "Parallel BM25 + Pinecone",
    technical: "Keyword search (SQLite FTS5) and dense vector search (Pinecone) run in parallel, then results are merged and deduplicated by chunk ID.",
    simple: "We search two different ways at once — by keyword and by meaning — so neither one's blind spots are fatal.",
  },
  {
    id: "rerank",
    stage: "Rerank",
    technical: "Candidates are rescored by relevance (IDF-weighted, length-normalized) and cut to the top 5.",
    simple: "We pick the 5 passages that actually answer the question, not just the ones that share words with it.",
  },
  {
    id: "generate",
    stage: "Sonnet generation",
    technical: "Claude Sonnet generates an answer strictly from the top 5 chunks, with inline citations, at temperature 0.",
    simple: "We write the answer, but only from what those 5 passages actually say.",
  },
  {
    id: "verify",
    stage: "Numerical verifier",
    technical: "Every number in the answer is checked by parsed magnitude against every number in the source chunks; anything ungrounded is replaced with an explicit qualifier.",
    simple: "We double-check every number in the answer is really in the source — or we say so.",
  },
  {
    id: "log",
    stage: "DynamoDB log",
    technical: "Query, rewritten query, retrieved chunks, answer, cost, and per-stage latency are logged for observability.",
    simple: "We keep a record of exactly what happened, in case something needs checking later.",
  },
] as const;

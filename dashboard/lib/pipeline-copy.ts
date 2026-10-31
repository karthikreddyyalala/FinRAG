// One entry per step of a call, in order. `rail` is the short label shown in
// the hero replay. Facts come from server/ (rate limit, cache, retrieval) and
// the 2026-10-30 deploy; the server runs no chat model.
export const PIPELINE_COPY = [
  {
    id: "pick",
    rail: "Pick tool",
    stage: "Claude picks a tool",
    technical: "The client's model reads the six tool descriptions over MCP streamable HTTP and calls one: get_company_financials for a reported figure (exact XBRL values for any company), search_sec_filings for anything written in a filing. No sign-in is involved.",
    simple: "Your AI assistant decides which of the six tools fits your question.",
  },
  {
    id: "limits",
    rail: "Limits + cache",
    stage: "Limits and cache",
    technical: "A shared rate limit (30 calls a minute, 1,000 a day across all users, kept in DynamoDB, fails open) runs first. Then identical calls are answered from a 24 hour cache. Degraded results are never cached.",
    simple: "A shared limit keeps the server fair for everyone. If the same call was made in the last day, the saved result comes back right away.",
  },
  {
    id: "filters",
    rail: "Filters",
    stage: "Ticker and year filters",
    technical: "A ticker and fiscal year are pulled from the call and applied as filters to both indexes. This stops a 2018 figure being drowned out by near-identical 2022 filings.",
    simple: "The server works out which company and which year you mean.",
  },
  {
    id: "expand",
    rail: "GAAP terms",
    stage: "GAAP expansion",
    technical: "A deterministic synonym table adds the filing's own line-item wording, for example \"capital expenditure\" becomes \"purchases of property, plant and equipment\". No model is involved.",
    simple: "Your wording is translated into the words a filing actually uses.",
  },
  {
    id: "retrieve",
    rail: "BM25 + Pinecone",
    stage: "BM25 and Pinecone",
    technical: "Keyword search (SQLite FTS5) and vector search (Pinecone, query embedded with OpenAI text-embedding-3-small) run in parallel, 40 candidates each. If the embedding fails, search falls back to keyword-only and says so in a note.",
    simple: "Two searches run at once, one by exact words and one by meaning, so a miss in one can be caught by the other.",
  },
  {
    id: "rerank",
    rail: "Full text + rerank",
    stage: "Full text and rerank",
    technical: "Each candidate is swapped for its full stored text (an indexed chunk_id lookup), because Pinecone only holds the first 1,000 characters. Voyage rerank-2.5, a neural cross-encoder, then scores every candidate against the question and keeps the top 5. A question naming a fiscal year but no quarter prefers the 10-K over 10-Qs. If Voyage is unreachable, a word-overlap scorer takes over.",
    simple: "Each hit is replaced by its complete passage, then the 5 best are kept.",
  },
  {
    id: "evidence",
    rail: "Evidence",
    stage: "Evidence returned",
    technical: "The tool returns up to 5 passages with their ids and citations, such as [MMM 10-K 2019-02-07], each capped at 8,000 characters. It does not return an answer.",
    simple: "You get the source passages, each labeled with the filing it came from.",
  },
  {
    id: "answer",
    rail: "Your model answers",
    stage: "Claude writes the answer",
    technical: "The client's own model (Claude, Cursor's model, and so on) writes the answer from those passages. The server runs no chat model at all.",
    simple: "Your own AI assistant writes the answer, using only what the passages say.",
  },
  {
    id: "verify",
    rail: "verify_figures",
    stage: "verify_figures",
    technical: "The client sends its answer and the passage ids. Every dollar amount, percentage and comma-grouped number is checked by parsed magnitude against the passages and returned as grounded or not_found. Units are not converted, so $1.58 billion does not match 1,577 (millions).",
    simple: "The dollar amounts and percentages in the answer are checked against the sources. Anything missing is flagged.",
  },
  {
    id: "log",
    rail: "Log",
    stage: "Log",
    technical: "Every tool call is logged to CloudWatch (kept 30 days) and to DynamoDB (expires after 90 days).",
    simple: "A record of each call is kept for up to 90 days in case something needs checking.",
  },
] as const;

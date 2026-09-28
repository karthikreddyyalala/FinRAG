// Real production bugs, verbatim from claude.md's "Why the corpus is being
// rebuilt" and D2 sections — not paraphrased away.
export const INCIDENTS = [
  {
    title: "Dense results silently discarded",
    symptom: "faithfulness scored 0.96 but every context metric scored ~0.0.",
    root_cause:
      "merge_and_dedup concatenated BM25-then-dense and rerank truncated with chunks[:top_k], so the top-5 was always 100% BM25 — every dense result was discarded before reranking ever saw it.",
    fix: "Hybrid search now actually merges both sources before the top-k cut.",
  },
  {
    title: "The substring verifier",
    symptom: "Fabricated figures passed the grounding check undetected.",
    root_cause:
      '"$1,234" is a literal substring of "$1,234.56" — a naive text-containment check treats a fabricated $1,234 as grounded whenever the source happens to contain a longer number that starts the same way.',
    fix: "Compare parsed numeric magnitude instead of raw text — see the verifier demo above.",
  },
  {
    title: "uuid4 chunk IDs",
    symptom: "Re-ingesting a filing duplicated every one of its chunks.",
    root_cause:
      "chunk_id was uuid4(), so every re-ingest generated fresh IDs. BM25 and Pinecone IDs never matched, so cross-source dedup silently couldn't work at all.",
    fix: "Chunk IDs are now content-addressed (sha256), so the same chunk always gets the same ID.",
  },
  {
    title: "The corpus held the wrong years",
    symptom: "147 of 150 FinanceBench questions were unanswerable.",
    root_cause:
      'list_filings defaulted to "last 2 10-Ks and 4 10-Qs" — in 2026 that means 2025-2026 filings, while FinanceBench asks about 2015-2024. The corpus had the right companies, just the wrong years.',
    fix: "Benchmark companies now ingest {10-K: 8, 10-Q: 12, 8-K: 8} — 28 filings each instead of 6.",
  },
  {
    title: "Unpinned temperature",
    symptom: "The identical question, through the identical fixed pipeline, was correct once and wrong once.",
    root_cause:
      'A coin flip at each API\'s default temperature (1.0) — the same query could return a correctly cited figure or "the context does not provide this figure" on two separate runs.',
    fix: "All four LLM call sites (Bedrock + OpenAI fallback, rewriter + generator) now pin temperature=0.",
  },
  {
    title: "The XBRL prior-year-comparative trap",
    symptom: "NVDA revenue was reported as $26,044M instead of the correct $44,062M.",
    root_cause:
      "A 10-Q's XBRL tags the prior-year comparative figure under the same fy/fp as the current quarter — a naive lookup grabbed last year's number for AAPL, NVDA, META, and GOOGL alike.",
    fix: "Ground-truth extraction now takes the maximum end date within the filing, not the first match.",
  },
] as const;

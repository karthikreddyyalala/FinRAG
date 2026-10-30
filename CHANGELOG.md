# Changelog

What changed, what was broken before, how it was found, and what it measured. Newest first. Every number here was measured on the same index on the same day as its "before", unless it says otherwise. Raw results are in `evals/results/` (gitignored, kept locally); the scripts that produce them are committed.

## 2026-10-30: Clean table text (M3, PR #21)

**Status: measuring.** Results go here before it ships.

**What was broken.** About 45% of the index (76,751 of 171,790 chunks) is tables, stored exactly as `pandas.read_html` serialized them:

```
0 | 1 | 2 | ... | 32
Net sales | Net sales | Net sales |  |  |  | $ | 12467.5 |  |  |  |  | $ | 9458.2 ...
```

The header row is column numbers instead of years, every merged cell is copied into each column it spans, and empty spacer columns are kept. A median table is 1,259 characters, of which 371 carry content. 3,599 tables ran past the 8,000-character passage cap, so the row a question asked about was often cut off before the model saw it.

**How it was found.** Sorting the 55 refusals left after the reranker change: in 11 of them the benchmark's own evidence page was among the 5 passages and the model still said "the context does not provide it". Reading those passages showed the tables above.

**What changed.**
- `clean_table_text` in `server/retrieval/evidence.py` rebuilds each table at serve time, before the reranker and the client see it: drops the column-number header and spacer columns, merges a merged cell's copies, and joins `$`, `(`, `)` and `%` to their number. No re-indexing.
- Two columns merge only if some row repeats the same value in both and no row disagrees, so two real years with equal values (0.20 and 0.20) stay apart, and blank cells keep their column.
- Checked on 3,000 random tables: no number is lost. Tables over the passage cap: 3,599 to 128.

**Also fixed: a refusal could count as correct.** The automated check matched stray numbers inside refusal text ("cannot determine ... 2022 ..."), so 11 of 55 refusals were scored as correct. `evals/failure_breakdown.py` now never scores a refusal as correct.

## 2026-10-30: Result cache served the previous build (M3, PR #21)

**What was broken.** Search results are cached for 24 hours, keyed by tool and arguments only. After the reranker deploy, "Netflix revenue FY2023" kept returning the old 10-Q passages, while a reworded question returned the 10-K.

**What changed.** The cache key includes a hash of the server's source (`CODE_VERSION` in `server/observability/tool_cache.py`), so any deploy that changes code starts with an empty cache. Verified live: the same question now returns the FY2023 10-K.

## 2026-10-30: Neural reranker and 10-K preference (M3, PR #21)

**What was broken.**
- Production never ran a neural reranker. The code expected a local cross-encoder, but the Lambda never installed `sentence-transformers`, so every search silently fell back to a word-overlap scorer. The right passage was in the top 5 for 13.4% of benchmark questions.
- "Netflix revenue FY2023" ranked quarterly 10-Qs above the annual 10-K that was in the index.

**What changed.**
- Voyage `rerank-2.5` (a hosted cross-encoder) ranks every search. If Voyage fails, the word-overlap scorer takes over and the search still answers. The dead local cross-encoder path is deleted.
- Candidates per search source: 10 to 40.
- A question that names a fiscal year but no quarter (or passes `fiscal_year`) drops 10-Qs when a 10-K was retrieved.

**Measured** (127 evidence questions, 92 number questions, 0 Voyage fallbacks):

| | Before | After |
|---|---|---|
| Evidence passage in top 5 | 13.4% | 45.7% |
| Evidence passage ranked first | 3.1% | 36.2% |
| Right number in top 5 | 52.2% | 63.0% |
| FinanceBench refused (of 150) | 99 | 55 |
| Right number among answered (of 110) | 25 | 49 |
| Answers with every figure in their passages | 96.7% | 84% |

- The 10-K preference alone moved evidence in top 5 from 13.4% to 22.0%.
- 40 candidates helped only with the neural reranker; the word-overlap scorer got slightly worse with them.
- The figure-check rate fell because more answers now compute ratios or convert units, which `verify_figures` does not do by design.
- Live: search 1.08 s median, 0.37 s cached. About 33K Voyage tokens per search (first 200M free, then about $0.0016 a search).

**Operational notes.** The Voyage key lives in SSM at `/finrag/voyage-api-key` and is required at cold start. Voyage needs a payment method on file: without one it allows 10K tokens a minute, and one search uses about 33K, so every search would fall back.

## 2026-10-30: Truth pass (PR #20)

**What was broken.** Server text, docs and the site had drifted from the real system: wrong company counts, page-number citations the chunks don't have, deploy steps that failed on a fresh account, and a CI eval that failed on every PR because its secrets were missing.

**What changed.** Server text, README, walkthrough and site match the deployed behaviour; deploy steps run from a fresh account; CI eval skips with a notice when secrets are missing; the unused Bedrock dependency is removed. Answer quality was re-measured on the live retrieval path: refusals 121 to 99, right number among answered 15 to 25 (of 110). The old correctness proxy counted numbers inside refusals as hits; it now counts answered questions only.

## 2026-10-30: Public evidence server (M1, PR #19)

**What was broken.**
- The account's Bedrock quota was 0. The old pipeline spent most of its 24 s per question waiting on throttled model calls, then silently fell back to gpt-4o-mini, so earlier evals were not written by the model the site named.
- Pinecone metadata holds only the first 1,000 characters of a chunk; 75% of chunks are longer (3,728 on average), so figures further down a table never reached the answer.
- The OpenAI account ran out of credits and the weekly refresh had been failing unnoticed since at least 2026-09-30.

**What changed.**
- The server returns cited passages and checks figures; the client's own model writes the answer. No chat model on the server, no sign-in.
- Six tools behind one guard: shared rate limit, 24 h cache, call logs. `verify_figures` lists every number not found in the cited passages.
- Every candidate is swapped for its full text before ranking. If embeddings fail, search falls back to keyword-only and says so.
- Health check every 5 minutes, alarms, 30-day log retention; Cognito and Bedrock removed.

**Measured.** Evidence in top 5: 10.2% to 13.4%; full text alone added 4.4 points to number-in-top-5. Live warm search 0.92 s median.

## Experiments that did not help (2026-10-24 to 2026-10-25)

Kept here so they are not repeated. Each was measured against the same baseline and reverted or left unused.

- **Analysing the lexical reranker's ordering:** no gain; the right number was missing from the candidates for about 39% of questions.
- **Table-row facts** (one chunk per statement row, 3 companies): correct 6 to 5, facts almost never reached the top 5. Removed.
- **Question cleaning** (strip persona and formatting boilerplate before search): within noise. Kept, since it is harmless.
- **Multi-search for ratio questions** (one search per needed line item): correct 15 to 12. Removed from the pipeline.

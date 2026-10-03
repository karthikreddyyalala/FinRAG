# Bugs that looked like answers

I spent a few months building a RAG system that answers financial questions from SEC filings. It returns a number, cites the filing it came from, and refuses when it can't find one.

For a good stretch of that time it was badly broken, and I had no idea, because it never crashed. It answered. The answers were fluent, well-cited, and confidently wrong in ways that took real work to even notice.

That turns out to be the thing nobody warns you about. In a normal backend, broken code throws. In RAG, broken code produces a paragraph. You read the paragraph, it sounds right, you move on. The system degrades silently and the output quality looks roughly the same the whole way down.

Here are the bugs that taught me that, and what each one looked like from the outside.

---

## 1. My hybrid search was keyword-only for weeks

The design was a standard hybrid retrieval setup. Run BM25 keyword search and dense vector search in parallel, merge the results, dedupe, rerank the merged pool, keep the top 5.

The merge looked like this: take the BM25 results, append the dense results, dedupe by chunk ID. Then the reranker took that list and sliced it with `chunks[:top_k]`.

Both of those are reasonable in isolation. Together they mean the dense results were never used. BM25 returned 10 results, the merged list started with all 10 of them, the reranker's slice took 5, and every single vector search result fell off the end. I was paying for embeddings, running the query, getting results back, and throwing all of them away.

The system worked fine. That's the problem. Keyword search on financial filings is decent, so the answers stayed plausible and I had no signal that half the retrieval stack was dead weight.

What gave it away wasn't the answers. It was the eval scores: faithfulness looked fine at 0.96 while every context metric sat near zero. That combination makes no sense, and chasing *why* those two disagreed is what surfaced the bug.

The fix was to interleave by rank rather than concatenate, so the truncation can't favor one source:

```python
for pair in zip_longest(bm25_chunks, normalized_pinecone):
    for chunk in pair:
        ...
```

Now the top-5 is BM25 #1, dense #1, BM25 #2, dense #2, and so on. The comment I left above it says the interleaving is load-bearing, because the next person to "simplify" it back into a concatenation would reintroduce the same silent failure.

**Lesson:** a merge function and a truncation function can each be correct and still combine into a bug. The seam between two correct components is where this stuff lives.

---

## 2. The grounding check that approved made-up numbers

The whole premise of this project is that every number in an answer has to appear in a retrieved source chunk. There's a verifier that runs after generation, pulls every number out of the answer, and checks each one against the sources. Anything it can't find gets replaced with an explicit "figure unavailable" marker.

The first version checked with a substring test. Is `"$1,234"` present anywhere in the source text?

`"$1,234"` is a substring of `"$1,234.56"`.

So if the model invented `$1,234` and the filing happened to contain `$1,234.56` somewhere, the verifier approved it. The exact failure the component existed to prevent, waved through by the component itself. And again: the output looked perfect. A cited number, a verifier that said OK, no error anywhere.

The fix is to stop comparing text and start comparing parsed values:

```python
def _is_grounded(number: str, source_values: set[float]) -> bool:
    value = _numeric_value(number)
    return value is not None and value in source_values
```

Parse every number in the sources into a set of floats, parse the candidate the same way, check membership. `1234 != 1234.56`, so the fabricated figure now gets caught.

This had a nice side effect I didn't plan. Financial tables split the currency symbol from the value and wrap negatives in parentheses, so a cash flow line reads `$ | (1,577)` while a correct answer says `$1,577 million`. Those share almost no literal substring. Comparing magnitudes handles both problems at once: it rejects `1234` against `1234.56`, and it accepts `$1,577` against `$(1,577)`.

**Lesson:** when you write a component whose entire job is catching a specific failure, write the test that proves it catches that failure. I had tests. None of them tested the case the thing existed for.

---

## 3. The corpus had the right companies and the wrong years

I benchmark against FinanceBench, a public set of 150 financial questions with verified answers. An early full run came back with the model saying "the context does not provide this figure" on nearly every question.

My first instinct was that retrieval was broken. It wasn't. The ingestion code pulled "the last 2 annual reports and last 4 quarterly reports" per company, which is a perfectly sensible default. Run that in 2026 and you get 2025 and 2026 filings. FinanceBench asks about 2015 through 2024.

So the corpus had exactly the right companies and almost none of the right years, and 147 of 150 questions were genuinely unanswerable from it. The model was behaving *correctly*. It was refusing to answer questions it had no data for, which is precisely what I built it to do. The refusal looked like a model quality problem and was actually a data coverage problem.

That's the part worth sitting with. The system's correct behavior and a serious bug produced identical-looking output.

**Lesson:** when a system refuses, check whether it's refusing for the right reason. "Model won't answer" and "model has nothing to answer from" look the same from the outside and have completely different fixes.

---

## 4. The same question, two different answers

At one point I ran the identical question through the identical pipeline twice and got a correct cited answer once and "the context does not provide this figure" the other time. Same code, same corpus, same query.

No temperature was pinned anywhere. Both the query rewriting call and the generation call were running at each provider's default, which is 1.0. Every question was a coin flip, and I'd been debugging retrieval for hours against a system whose output I couldn't reproduce.

The fix is three characters in four places:

```python
inferenceConfig={"temperature": 0},
```

That's it. Rewriter and generator, Bedrock path and the OpenAI fallback path, all four call sites.

**Lesson:** pin temperature before you debug anything, not after. Non-determinism doesn't just add noise, it actively destroys your ability to tell whether a change helped. I "fixed" things during that window that may have needed no fixing.

---

## 5. The vocabulary gap

A user asks "what was 3M's capital expenditure in FY2018?"

The phrase "capital expenditure" does not appear in a cash flow statement. The line item is "Purchases of property, plant and equipment (PP&E)."

Zero term overlap. BM25 has nothing to match on. And the dense embedding isn't reliably rescuing you either, because in embedding space a jargon-heavy accounting phrase and its plain-English name aren't as close as you'd hope.

I fixed this with a deterministic synonym expansion that runs after the LLM rewrite:

```python
GAAP_SYNONYMS = {
    "capital expenditure": "purchases of property plant and equipment PP&E capital spending",
    "capex": "purchases of property plant and equipment PP&E capital spending",
    "revenue": "net sales total revenues",
    "cogs": "cost of sales cost of goods sold",
    ...
}
```

Boring, hardcoded, not clever. It also works, and unlike asking an LLM to do the expansion, it does the same thing every time.

**Lesson:** your users' vocabulary and your corpus's vocabulary are different languages, and the gap is widest in exactly the specialized domains where RAG is most worth doing. A lookup table is a legitimate answer.

---

## The part where my pipeline lost

After fixing all of that, I did what I should have done earlier: ran the same 150 benchmark questions through three configurations to find out whether my four-stage pipeline was actually earning its complexity.

| Configuration | Numerical accuracy | Faithfulness |
|---|---|---|
| Dense (vector) search only | 86.5% | 79.4% |
| **BM25 (keyword) search only** | **94.4%** | **83.8%** |
| Full pipeline (rewrite + hybrid + rerank + verify) | 91.0% | 79.4% |

Plain keyword search beat my full pipeline.

I sat with that for a while before publishing it. The honest reading: FinanceBench's questions are worded close to how the filings themselves say things, which is close to a best case for lexical matching. The full pipeline does clearly beat dense-only search, by about 4.5 points of numerical accuracy, which tells me the hybrid part is doing real work exactly where embeddings alone miss keyword-heavy financial terms. A harder or more paraphrased question set would likely shift this.

But I can't claim that from this data, because I didn't measure it. What I measured says keyword search won.

The reason I'm publishing the table instead of the one flattering row is that the alternative is how you end up believing your own pipeline diagram. Every bug above survived as long as it did because the output looked good enough that I didn't go check. A benchmark that only ever confirms your design does the same thing, more formally.

---

## What I'd tell myself at the start

**Fluent output is not a signal.** It's the default. A RAG system will produce a confident, well-formatted, correctly-cited paragraph whether or not any part of it is working. You need signals that are independent of how good the answer sounds.

**Disagreeing metrics are a gift.** The single most useful debugging event in this project was faithfulness at 0.96 alongside context metrics near zero. That contradiction was the only reason I found the discarded-dense bug. If every metric had been mediocre and consistent, I'd have shrugged and tuned a prompt.

**Test the specific failure each component exists to prevent.** Not the happy path. The verifier had tests. None of them tested a fabricated number against a longer real one, which was the entire point of the verifier.

**Pin your temperature first.** Before any debugging, any evaluation, any "did that help" comparison.

**Publish the result that makes you look worse.** It's the only part of a writeup like this that's hard to fake, and it's the part that forced me to actually understand where my design helps and where it's just complexity I'm attached to.

---

*The project is open source, including the eval harness and all the numbers above: [github.com/karthikreddyyalala/FinRAG](https://github.com/karthikreddyyalala/FinRAG). There's a live site with an interactive version of the numerical verifier, where you can edit a figure and watch it get flagged, at [dashboard-weld-nine-28.vercel.app](https://dashboard-weld-nine-28.vercel.app).*

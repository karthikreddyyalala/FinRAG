"""Evidence retrieval for the MCP tools. No chat model anywhere on this path.

The client's model (Claude, Cursor, ...) writes the answer; the server finds
passages and checks figures. Measured on 2026-10-29: this account's Bedrock
quota is 0, so the old rewrite -> generate pipeline spent most of its ~24 s
waiting on throttles before silently falling back to OpenAI, and timed out at
120 s whenever calls overlapped.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from server.retrieval.hybrid_retriever import hybrid_search
from server.retrieval.query_cleaner import clean_question
from server.retrieval.query_filters import extract_filters, period_window, wants_annual
from server.retrieval.query_rewriter import expand_financial_terms
from server.retrieval.reranker import rerank, voyage_tokens

# A large schedule table can run to tens of thousands of characters; one such
# chunk must not flood the client's context on its own.
MAX_PASSAGE_CHARS = 8000
# Measured 2026-10-30 (127 evidence questions, top 5): 10 per source with the
# lexical scorer 22.0%, 40 with Voyage 45.7%. Deeper pools only pay off with a
# neural reranker; lexical scoring got worse at 40 (23.6%, number metric down).
CANDIDATES_PER_SOURCE = 40
KEYWORD_ONLY_NOTE = "Keyword search only: semantic search is unavailable right now."
BUDGET_NOTE = ("Ranked by keyword overlap: today's reranking budget is used up, so these "
               "passages may be less relevant. It resets at 00:00 UTC.")
NO_MATCH_NOTE = (
    "No passages matched. Try the filing's own wording or a different year, "
    "or call list_covered_companies."
)


def find_passages(
    question: str,
    pinecone_index: Any,
    keyword_index: Any,
    embed_fn: Callable[[str], list[float]],
    ticker: str | None = None,
    years: tuple[int, int] | None = None,
    top_k: int = 5,
    stage: str = "reranked",
    voyage_budget: Callable[[int], bool] | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Find the chunks that best answer a question.

    Args:
        question: The question in the client's words.
        pinecone_index: A Pinecone Index handle.
        keyword_index: sync_pinecone.KeywordIndex over the full corpus.
        embed_fn: Callable(text) -> embedding vector (the corpus's model).
        ticker: Restrict to this company. Passed explicitly, it is strict:
            other companies' chunks are dropped, never returned as a
            fallback. When None, a company named in the question is a soft
            filter (hybrid_search widens if it matches nothing).
        years: (first, last) fiscal years; when None, years in the question.
        top_k: Chunks to keep after reranking.
        stage: "reranked" (default) or "candidates" (everything retrieved,
            before reranking, for evals and the health check).
        voyage_budget: Called with the tokens a Voyage rerank would bill;
            False means rank by keyword overlap instead. None: no cap (evals).

    Returns:
        (chunks, note). note is None, or a short message for the client:
        keyword-only fallback, or nothing matched.
    """
    if stage not in ("candidates", "reranked"):
        raise ValueError(f"unknown stage {stage!r}; expected 'candidates' or 'reranked'")

    # Instructions like "Round your answer..." add words no filing contains.
    ticker = ticker.upper() if ticker else None
    search_query = clean_question(question)
    if not search_query.strip():
        raise ValueError("question is empty")
    # "capital expenditure" never appears in a cash flow statement; "purchases
    # of property, plant and equipment" does.
    lexical_query = expand_financial_terms(search_query)
    found = extract_filters(question)
    filter_ticker = ticker or found["ticker"]
    filter_years = years or found["years"]
    period_range = period_window(filter_years) if filter_years else None

    note = None
    try:
        candidates = hybrid_search(
            lexical_query, keyword_index, pinecone_index, embed_fn,
            top_k=CANDIDATES_PER_SOURCE, ticker=filter_ticker, period_range=period_range,
        )
    except Exception as exc:
        # Semantic search needs an OpenAI embedding call. With OpenAI down or
        # out of credits (2026-10-28), keyword search still answers most
        # questions, and the client is told which mode it got.
        print(f"finrag: semantic search failed ({type(exc).__name__}: {exc}); "
              "keyword search only", flush=True)
        candidates = _keyword_only(lexical_query, keyword_index, filter_ticker, period_range)
        note = KEYWORD_ONLY_NOTE

    if ticker:
        candidates = [c for c in candidates if (c.get("ticker") or "").upper() == ticker]
    candidates = _with_full_text(candidates, keyword_index)
    if wants_annual(question, years) and any(c.get("filing_type") == "10-K" for c in candidates):
        candidates = [c for c in candidates if c.get("filing_type") != "10-Q"]

    if stage == "candidates":
        chunks = candidates
    else:
        use_voyage = voyage_budget is None or voyage_budget(voyage_tokens(search_query, candidates))
        chunks = rerank(search_query, candidates, top_k=top_k, lexical_query=lexical_query,
                        use_voyage=use_voyage)
        if not use_voyage:
            note = f"{note} {BUDGET_NOTE}" if note else BUDGET_NOTE
    if not chunks:
        note = f"{note} {NO_MATCH_NOTE}" if note == KEYWORD_ONLY_NOTE else NO_MATCH_NOTE
    elif stage == "reranked" and years and period_range and not any(
        period_range[0] <= (c.get("period") or "") <= period_range[1] for c in chunks
    ):
        span = str(years[0]) if years[0] == years[1] else f"{years[0]}-{years[1]}"
        year_note = f"No filings matched {span}; these passages are from other years."
        note = f"{note} {year_note}" if note else year_note
    return chunks, note


def _keyword_only(
    query: str, keyword_index: Any, ticker: str | None, period_range: tuple[str, str] | None
) -> list[dict[str, Any]]:
    """BM25 alone, with hybrid_search's rule: a filter that finds nothing is dropped."""
    if ticker or period_range:
        results = keyword_index.search(
            query, CANDIDATES_PER_SOURCE, ticker=ticker, period_range=period_range
        )
        if results:
            return results
    return keyword_index.search(query, CANDIDATES_PER_SOURCE)


# Cells that belong to the number next to them: "$ | 1,577", "(17 | )", "3.5 | %".
_SYMBOLS = frozenset({"$", "(", ")", "%", ")%"})
_FLOAT_INT = re.compile(r"^(-?\d+)\.0$")


def clean_table_text(text: str) -> str:
    """Undo pd.read_html's serialization of a filing table, keeping every value.

    45% of chunks are tables stored as read_html left them: a "0 | 1 | ... | 32"
    header, every merged cell copied into each column it spans, empty spacer
    columns. About 75% of their characters are noise, 3,599 of them overflow the
    8,000-character passage cap, and the model refused on tables whose figures
    it had been given (Amcor FY2020 net receivables, 2026-10-30).

    Two columns are one logical column only if no row holds two different
    values in them, so real neighbouring years (0.20 | 0.20) stay apart: their
    header row differs. Empty cells inside a row are kept to hold alignment.
    """
    lines = text.split("\n")
    header = [c.strip() for c in lines[0].split(" | ")]
    if len(header) < 2 or header != [str(i) for i in range(len(header))]:
        return text
    # read_html stores a merged year header once as "2026" and once as "2026.0".
    rows = [[_FLOAT_INT.sub(r"\1", c.strip()) for c in line.split(" | ")] for line in lines[1:]]
    width = max(len(r) for r in rows) if rows else 0
    rows = [r + [""] * (width - len(r)) for r in rows]

    def value(cell: str) -> str:
        return "" if cell in _SYMBOLS else cell

    groups: list[list[int]] = []
    for col in range(width):
        if not any(r[col] for r in rows):
            continue  # spacer column
        if groups and _same_column(rows, groups[-1], col, value):
            groups[-1].append(col)
        else:
            groups.append([col])

    out = []
    for r in rows:
        cells = []
        for group in groups:
            parts: list[str] = []
            for col in group:
                if r[col] and not (parts and r[col] == parts[-1]):
                    parts.append(r[col])
            cells.append("".join(parts))
        while cells and not cells[-1]:
            cells.pop()
        if cells:
            out.append(" | ".join(cells))
    return "\n".join(out)


def _same_column(rows: list[list[str]], group: list[int], col: int, value: Any) -> bool:
    """Is `col` a copy of (or the $ / % beside) the logical column `group`?

    Never when a row holds two different values. Otherwise only on evidence:
    one side is symbols only, or some row repeats the same value in both, as
    a merged cell's copies always do. Blank cells alone prove nothing.
    """
    group_vals = [{value(r[g]) for g in group} - {""} for r in rows]
    col_vals = [value(r[col]) for r in rows]
    if any(v and gv and gv != {v} for v, gv in zip(col_vals, group_vals)):
        return False
    return (
        not any(col_vals)
        or not any(group_vals)
        or any(v and gv == {v} for v, gv in zip(col_vals, group_vals))
    )


def _with_full_text(chunks: list[dict[str, Any]], keyword_index: Any) -> list[dict[str, Any]]:
    """Swap each chunk for its full text from the keyword index.

    Dense hits come from Pinecone metadata, which keeps only the first 1,000
    characters. 75% of chunks are longer (3,728 on average), so a figure
    further down a table never reached the answer. Tables are cleaned here,
    before the reranker and the client see them.
    """
    full = keyword_index.get_by_ids([c["chunk_id"] for c in chunks])
    hydrated = [full.get(c["chunk_id"], c) for c in chunks]
    return [{**c, "text": clean_table_text(c.get("text") or "")} for c in hydrated]


def format_citation(chunk: dict[str, Any]) -> str:
    """Citation like [TICKER FORM FILED p.N]; the page is omitted when unknown (HTML filings)."""
    base = f"[{chunk['ticker']} {chunk['filing_type']} {chunk['period']}"
    if chunk.get("page_number") is not None:
        return f"{base} p.{chunk['page_number']}]"
    return f"{base}]"


def to_passage(chunk: dict[str, Any]) -> dict[str, Any]:
    """The shape every tool returns for one piece of evidence."""
    text = chunk.get("text") or ""
    if len(text) > MAX_PASSAGE_CHARS:
        text = text[:MAX_PASSAGE_CHARS] + " [... truncated]"
    return {
        "id": chunk["chunk_id"],
        "ticker": chunk.get("ticker"),
        "form": chunk.get("filing_type"),
        "filed": chunk.get("period"),
        "page": chunk.get("page_number"),
        "citation": format_citation(chunk),
        "text": text,
    }

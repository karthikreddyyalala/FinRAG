"""Evidence retrieval for the MCP tools. No chat model anywhere on this path.

The client's model (Claude, Cursor, ...) writes the answer; the server finds
passages and checks figures. Measured on 2026-10-29: this account's Bedrock
quota is 0, so the old rewrite -> generate pipeline spent most of its ~24 s
waiting on throttles before silently falling back to OpenAI, and timed out at
120 s whenever calls overlapped.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from server.retrieval.hybrid_retriever import hybrid_search
from server.retrieval.query_cleaner import clean_question
from server.retrieval.query_filters import extract_filters, period_window
from server.retrieval.query_rewriter import expand_financial_terms
from server.retrieval.reranker import rerank

# A large schedule table can run to tens of thousands of characters; one such
# chunk must not flood the client's context on its own.
MAX_PASSAGE_CHARS = 8000
CANDIDATES_PER_SOURCE = 10
KEYWORD_ONLY_NOTE = "Keyword search only: semantic search is unavailable right now."
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
            before reranking, for evals).

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

    if stage == "candidates":
        chunks = candidates
    else:
        chunks = rerank(search_query, candidates, top_k=top_k, lexical_query=lexical_query)
    if not chunks:
        note = f"{note} {NO_MATCH_NOTE}" if note == KEYWORD_ONLY_NOTE else NO_MATCH_NOTE
    elif stage == "reranked" and years and period_range and not any(
        period_range[0] <= (c.get("period") or "") <= period_range[1] for c in chunks
    ):
        span = str(years[0]) if years[0] == years[1] else f"{years[0]}-{years[1]}"
        note = f"No filings matched {span}; these passages are from other years."
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


def _with_full_text(chunks: list[dict[str, Any]], keyword_index: Any) -> list[dict[str, Any]]:
    """Swap each chunk for its full text from the keyword index.

    Dense hits come from Pinecone metadata, which keeps only the first 1,000
    characters. 75% of chunks are longer (3,728 on average), so a figure
    further down a table never reached the answer.
    """
    full = keyword_index.get_by_ids([c["chunk_id"] for c in chunks])
    return [full.get(c["chunk_id"], c) for c in chunks]


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

"""TDD: the lexical fallback must not reward chunks for being verbose.

Scoring by "fraction of query terms present" lets a long prose chunk win on
generic words -- company, cash, amount, fiscal, year -- while the short table
that actually holds the figure loses. Measured on FinanceBench Q1: an
irrelevant LIBOR passage scored 0.769 against the correct cash-flow table's
0.423, so the answer was unreachable even though retrieval had found it.

Terms are weighted by how well they discriminate within the candidate set:
a word in nearly every candidate says nothing about which one to pick.

Every test here calls rerank() and is really testing the LEXICAL scorer's
own behavior. conftest.py's autouse `_force_lexical_reranker` fixture
forces that path for the whole tests/unit/ suite -- see it for why."""
from server.retrieval.reranker import rerank

# Shape mirrors the real failure: verbose prose padded with generic finance
# vocabulary vs. the concise table holding the answer.
VERBOSE_PROSE = (
    "3M maintains a strong liquidity profile. The Company's primary short-term "
    "liquidity needs are met through cash on hand. In fiscal year 2018 the total "
    "amount of cash available in USD millions provided information the Company "
    "presented regarding capital spending and cash flow of the business."
)
CORRECT_TABLE = (
    "Purchases of property, plant and equipment (PP&E) | $ | (1,577) | $ | (1,373) "
    "| Proceeds from sale of PP&E and other assets | 262 | 49"
)
QUERY = (
    "fiscal year 2018 capital expenditure amount USD millions 3M Company cash flow "
    "statement purchases of property plant and equipment PP&E capital spending"
)


# Retrieval returns ~19 candidates, nearly all prose from the same 10-K, so
# generic finance vocabulary is common across them and carries no signal.
# One candidate is the table holding the figure. This is the real shape of
# the FinanceBench Q1 failure, and IDF needs that spread to mean anything.
OTHER_PROSE = [
    "The Company's effective tax rate for fiscal year 2018 reflected the amount "
    "of cash taxes presented in USD millions for the Company.",
    "Return on Invested Capital is a non-GAAP measure the Company presented "
    "for fiscal year 2018 covering capital and cash flow information.",
    "In fiscal year 2018 the Company reported total amount of cash flow from "
    "operations in USD millions as presented in this statement.",
    "Financial Conduct Authority announced LIBOR changes affecting the Company "
    "and its capital and cash flow in fiscal year 2018, amount in USD millions.",
    "The Company's pension obligations for fiscal year 2018 presented the total "
    "amount of cash contributions in USD millions.",
]


def test_concise_answer_beats_verbose_prose():
    chunks = [{"chunk_id": f"prose{i}", "text": t} for i, t in enumerate(OTHER_PROSE)]
    chunks.append({"chunk_id": "prose_main", "text": VERBOSE_PROSE})
    chunks.append({"chunk_id": "table", "text": CORRECT_TABLE})

    top = rerank(QUERY, chunks, top_k=1)
    assert top[0]["chunk_id"] == "table", (
        "verbose prose outranked the chunk holding the figure"
    )


def test_discriminative_terms_outweigh_ubiquitous_ones():
    """A term in every candidate cannot distinguish between them."""
    common = "the company reported results for the fiscal year"
    chunks = [
        {"chunk_id": "a", "text": f"{common} revenue segment detail"},
        {"chunk_id": "b", "text": f"{common} inventory detail"},
        {"chunk_id": "target", "text": f"{common} purchases of property plant equipment"},
    ]
    top = rerank("company fiscal year purchases of property plant equipment", chunks, top_k=1)
    assert top[0]["chunk_id"] == "target"


def test_still_returns_top_k_chunks():
    chunks = [{"chunk_id": f"c{i}", "text": f"chunk text {i}"} for i in range(10)]
    assert len(rerank("chunk text", chunks, top_k=5)) == 5


def test_empty_candidates_returns_empty():
    assert rerank("anything", [], top_k=5) == []


def test_chunk_with_no_overlap_ranks_last():
    chunks = [
        {"chunk_id": "unrelated", "text": "weather patterns in the pacific northwest"},
        {"chunk_id": "relevant", "text": "purchases of property plant and equipment"},
    ]
    top = rerank("purchases of property plant and equipment", chunks, top_k=2)
    assert top[0]["chunk_id"] == "relevant"

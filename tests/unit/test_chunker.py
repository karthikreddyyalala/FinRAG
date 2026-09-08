from pipeline.chunker import chunk_filing, chunk_tables, chunk_text_blocks

METADATA = {"ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026"}


def test_chunk_text_blocks_flushes_child_chunk_at_word_limit():
    blocks = ["word " * 100 for _ in range(5)]  # 5 blocks x 100 words = 500 words

    chunks = chunk_text_blocks(blocks, METADATA)

    child_chunks = [c for c in chunks if c["chunk_type"] == "child"]
    assert len(child_chunks) >= 1
    assert child_chunks[0]["ticker"] == "NVDA"
    assert child_chunks[0]["page_number"] is None


def test_chunk_text_blocks_flushes_remaining_short_content():
    blocks = ["short block of text here"]

    chunks = chunk_text_blocks(blocks, METADATA)

    assert len(chunks) == 2  # one parent, one child, both under the word limit
    assert {c["chunk_type"] for c in chunks} == {"parent", "child"}


def test_chunk_tables_creates_one_chunk_per_table_with_structure_preserved():
    tables = [{"headers": ["Segment", "Revenue"], "rows": [["Data Center", "9000"]]}]

    chunks = chunk_tables(tables, METADATA)

    assert len(chunks) == 1
    assert chunks[0]["chunk_type"] == "table"
    assert chunks[0]["table_headers"] == ["Segment", "Revenue"]
    assert "Data Center" in chunks[0]["text"]
    assert chunks[0]["ticker"] == "NVDA"


def test_chunk_filing_combines_text_and_table_chunks():
    processed = {
        "text_blocks": ["a reasonably long block of filing text content here"],
        "tables": [{"headers": ["A", "B"], "rows": [["1", "2"]]}],
        "metadata": METADATA,
    }

    chunks = chunk_filing(processed)

    types = {c["chunk_type"] for c in chunks}
    assert types == {"parent", "child", "table"}

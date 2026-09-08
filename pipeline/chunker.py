"""Hierarchical chunking of processed filing text and tables.

Splits processed filing output (from html_processor.py) into parent, child,
and table chunks, each tagged with filing metadata so downstream retrieval
can filter and cite precisely.

Token counts are approximated by whitespace word count. This is a Week 1
placeholder for a real tokenizer, documented as such -- exact token budgets
aren't load-bearing until reranking/generation limits are enforced in
Week 2+.
"""
from __future__ import annotations

import uuid
from typing import Any

PARENT_CHUNK_WORDS = 1500
CHILD_CHUNK_WORDS = 400


def _word_count(text: str) -> int:
    return len(text.split())


def _new_chunk(
    text: str, chunk_type: str, section: str, metadata: dict[str, Any]
) -> dict[str, Any]:
    return {
        "chunk_id": str(uuid.uuid4()),
        "text": text,
        "chunk_type": chunk_type,
        "section": section,
        "page_number": None,  # HTML filings have no native pagination
        **metadata,
    }


def chunk_text_blocks(
    text_blocks: list[str], metadata: dict[str, Any]
) -> list[dict[str, Any]]:
    """Group text blocks into parent (~1500 word) and child (~400 word) chunks.

    Args:
        text_blocks: Ordered text blocks from html_processor.process_filing().
        metadata: Filing-level metadata to attach to every chunk (ticker,
            filing_type, period, company_name, etc.).

    Returns:
        List of parent and child chunk dicts.
    """
    chunks: list[dict[str, Any]] = []

    parent_buffer: list[str] = []
    parent_words = 0
    child_buffer: list[str] = []
    child_words = 0
    section = "body"

    def flush_child() -> None:
        nonlocal child_buffer, child_words
        if child_buffer:
            chunks.append(_new_chunk(" ".join(child_buffer), "child", section, metadata))
        child_buffer = []
        child_words = 0

    def flush_parent() -> None:
        nonlocal parent_buffer, parent_words
        if parent_buffer:
            chunks.append(_new_chunk(" ".join(parent_buffer), "parent", section, metadata))
        parent_buffer = []
        parent_words = 0

    for block in text_blocks:
        words = _word_count(block)

        parent_buffer.append(block)
        parent_words += words
        if parent_words >= PARENT_CHUNK_WORDS:
            flush_parent()

        child_buffer.append(block)
        child_words += words
        if child_words >= CHILD_CHUNK_WORDS:
            flush_child()

    flush_parent()
    flush_child()

    return chunks


def chunk_tables(
    tables: list[dict[str, Any]], metadata: dict[str, Any]
) -> list[dict[str, Any]]:
    """Convert each extracted table into one chunk with structured metadata.

    Args:
        tables: Table dicts from html_processor.process_filing().
        metadata: Filing-level metadata to attach to every chunk.

    Returns:
        One chunk dict per table, with headers/rows serialized into the
        chunk text for embedding, and preserved structurally too.
    """
    chunks = []
    for table in tables:
        header_line = " | ".join(table["headers"])
        row_lines = [" | ".join(row) for row in table["rows"]]
        text = "\n".join([header_line, *row_lines])

        chunk = _new_chunk(text, "table", "table", metadata)
        chunk["table_headers"] = table["headers"]
        chunk["table_rows"] = table["rows"]
        chunks.append(chunk)
    return chunks


def chunk_filing(processed: dict[str, Any]) -> list[dict[str, Any]]:
    """Chunk a fully processed filing (text + tables) into all chunk types.

    Args:
        processed: Output of html_processor.process_filing(): {"text_blocks",
            "tables", "metadata"}.

    Returns:
        Combined list of parent, child, and table chunks.
    """
    metadata = processed["metadata"]
    return [
        *chunk_text_blocks(processed["text_blocks"], metadata),
        *chunk_tables(processed["tables"], metadata),
    ]

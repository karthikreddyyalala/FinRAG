"""Extracts text and tables from SEC filing HTML using BeautifulSoup + pandas.

SEC EDGAR serves 10-Q/10-K filings as HTML, not PDF, so this module replaces
the pdfplumber-based extraction originally specified in CLAUDE.md with an
HTML-native equivalent that reads the same raw bytes edgar_client.py stores.
"""
from __future__ import annotations

from io import StringIO
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup

MIN_TEXT_BLOCK_CHARS = 40  # skip boilerplate fragments (nav labels, single words)
TEXT_TAGS = ["p", "div", "span", "h1", "h2", "h3", "td"]


def extract_text_blocks(soup: BeautifulSoup) -> list[str]:
    """Extract non-trivial text blocks, preserving section-like breaks.

    Args:
        soup: Parsed filing HTML.

    Returns:
        List of text blocks, one per paragraph/section-like element, with
        blocks shorter than MIN_TEXT_BLOCK_CHARS dropped. Only leaf-most
        matching elements are extracted -- a <div> wrapping a <p> is
        skipped so its text isn't captured twice.
    """
    blocks: list[str] = []
    for tag in soup.find_all(TEXT_TAGS):
        if tag.find(TEXT_TAGS):
            continue  # descendant will be captured on its own iteration
        text = tag.get_text(separator=" ", strip=True)
        if len(text) >= MIN_TEXT_BLOCK_CHARS:
            blocks.append(text)
    return blocks


def extract_tables(html: str) -> list[dict[str, Any]]:
    """Extract structured tables from filing HTML using pandas.read_html.

    Args:
        html: Raw filing HTML content.

    Returns:
        List of {"headers": [...], "rows": [[...], ...]} dicts, one per
        table found. Tables that fail to parse cleanly are skipped.
    """
    tables: list[dict[str, Any]] = []
    try:
        dataframes = pd.read_html(StringIO(html))
    except Exception:
        return tables

    for df in dataframes:
        if df.empty or df.shape[1] < 2:
            continue
        df = df.fillna("")
        headers = [str(c) for c in df.columns]
        rows = df.astype(str).values.tolist()
        tables.append({"headers": headers, "rows": rows})
    return tables


def process_filing(html: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """Process one filing's HTML into the standard extraction schema.

    Args:
        html: Raw filing HTML content, as stored by edgar_client.py.
        metadata: Filing metadata (ticker, filing_type, period, etc.) to
            attach unchanged to the output.

    Returns:
        {"text_blocks": [...], "tables": [...], "metadata": {...}}
    """
    soup = BeautifulSoup(html, "lxml")
    return {
        "text_blocks": extract_text_blocks(soup),
        "tables": extract_tables(html),
        "metadata": metadata,
    }

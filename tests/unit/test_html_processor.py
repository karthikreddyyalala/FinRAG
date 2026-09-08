from bs4 import BeautifulSoup

from pipeline.html_processor import extract_tables, extract_text_blocks, process_filing

SAMPLE_HTML = """
<html><body>
<h2>Item 1. Financial Statements</h2>
<p>Net revenue increased due to strong data center demand this quarter.</p>
<table>
<tr><th>Segment</th><th>Q1 2024</th><th>Q1 2026</th></tr>
<tr><td>Data Center</td><td>4000</td><td>9000</td></tr>
</table>
<p>ok</p>
</body></html>
"""


def test_extract_text_blocks_drops_short_fragments():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")

    blocks = extract_text_blocks(soup)

    assert any("data center demand" in b.lower() for b in blocks)
    assert "ok" not in blocks


def test_extract_text_blocks_skips_nested_wrapper_to_avoid_duplication():
    nested_html = """
    <html><body>
    <div><p>Net revenue increased due to strong data center demand this quarter.</p></div>
    </body></html>
    """
    soup = BeautifulSoup(nested_html, "lxml")

    blocks = extract_text_blocks(soup)

    assert blocks == ["Net revenue increased due to strong data center demand this quarter."]


def test_extract_tables_returns_headers_and_rows():
    tables = extract_tables(SAMPLE_HTML)

    assert len(tables) == 1
    assert tables[0]["headers"] == ["Segment", "Q1 2024", "Q1 2026"]
    assert tables[0]["rows"] == [["Data Center", "4000", "9000"]]


def test_process_filing_returns_full_schema_with_metadata():
    metadata = {"ticker": "NVDA", "filing_type": "10-Q", "period": "Q1-2026"}

    result = process_filing(SAMPLE_HTML, metadata)

    assert result["metadata"] == metadata
    assert len(result["tables"]) == 1
    assert len(result["text_blocks"]) >= 1

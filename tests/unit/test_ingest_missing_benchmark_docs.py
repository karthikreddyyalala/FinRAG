from scripts.ingest_missing_benchmark_docs import merge_chunks, plan_by_ticker


def test_plan_groups_missing_docs_by_ticker_with_year_quarter_form():
    rows = [
        {"doc_name": "JPMORGAN_2021Q1_10Q", "company": "JPMorgan"},
        {"doc_name": "JPMORGAN_2022_10K", "company": "JPMorgan"},
        {"doc_name": "WALMART_2018_10K", "company": "Walmart"},
    ]
    plan = plan_by_ticker(
        ["JPMORGAN_2021Q1_10Q", "JPMORGAN_2022_10K", "WALMART_2018_10K"], rows
    )
    assert plan == {
        "JPM": [(2021, 1, "10-Q"), (2022, None, "10-K")],
        "WMT": [(2018, None, "10-K")],
    }


def test_merge_chunks_keeps_existing_and_skips_duplicate_ids():
    existing = [{"chunk_id": "a"}, {"chunk_id": "b"}]
    new = [{"chunk_id": "b"}, {"chunk_id": "c"}]
    merged = merge_chunks(existing, new)
    assert [c["chunk_id"] for c in merged] == ["a", "b", "c"]

from pipeline.edgar_history import all_submission_rows, select_filings

PAGE_RECENT = {
    "filings": {
        "recent": {
            "form": ["10-K", "4"],
            "reportDate": ["2025-06-30", ""],
            "filingDate": ["2025-07-30", "2025-08-01"],
            "accessionNumber": ["0000-25-1", "0000-25-2"],
            "primaryDocument": ["a.htm", "b.xml"],
        },
        "files": [{"name": "CIK0000789019-submissions-001.json"}],
    }
}
PAGE_OLD = {
    "form": ["10-K", "10-Q"],
    "reportDate": ["2016-06-30", "2016-03-31"],
    "filingDate": ["2016-07-28", "2016-04-21"],
    "accessionNumber": ["0000-16-1", "0000-16-2"],
    "primaryDocument": ["msft10k.htm", "msft10q.htm"],
}


def test_all_submission_rows_reads_recent_and_older_pages():
    seen = []

    def get_json(url):
        seen.append(url)
        return PAGE_OLD if url.endswith("submissions-001.json") else PAGE_RECENT

    rows = all_submission_rows(789019, get_json)
    assert seen[1].endswith("/submissions/CIK0000789019-submissions-001.json")
    assert {r["accessionNumber"] for r in rows} == {
        "0000-25-1", "0000-25-2", "0000-16-1", "0000-16-2",
    }
    assert rows[0] == {
        "form": "10-K", "reportDate": "2025-06-30", "filingDate": "2025-07-30",
        "accessionNumber": "0000-25-1", "primaryDocument": "a.htm",
    }


def test_select_filings_matches_fiscal_year_by_report_date():
    rows = all_submission_rows(789019, lambda u: PAGE_OLD if "001" in u else PAGE_RECENT)
    wanted = [(2016, None, "10-K"), (2016, 1, "10-Q")]
    picked = select_filings(wanted, rows)
    assert [(r["form"], r["filingDate"]) for r in picked] == [
        ("10-K", "2016-07-28"), ("10-Q", "2016-04-21"),
    ]


def test_select_filings_skips_filings_it_cannot_find():
    assert select_filings([(1999, None, "10-K")], []) == []

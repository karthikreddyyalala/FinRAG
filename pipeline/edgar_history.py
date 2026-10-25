"""Find older filings that EDGAR's "recent" list no longer carries.

submissions/CIK*.json holds only a company's latest ~1000 filings under
filings.recent; anything older sits in extra pages listed under filings.files.
list_filings() reads only the recent block, which is why 2015-2017 annual
reports were never ingested for companies that file many forms.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pipeline.edgar_client import SUBMISSIONS_URL

FIELDS = ("form", "reportDate", "filingDate", "accessionNumber", "primaryDocument")
PAGE_URL = "https://data.sec.gov/submissions/{name}"


def _rows(block: dict[str, list[str]]) -> list[dict[str, str]]:
    return [dict(zip(FIELDS, values)) for values in zip(*(block[f] for f in FIELDS))]


def all_submission_rows(cik: int, get_json: Callable[[str], dict[str, Any]]) -> list[dict[str, str]]:
    """Every filing row for a company: the recent block plus each older page."""
    first = get_json(SUBMISSIONS_URL.format(cik=cik))
    rows = _rows(first["filings"]["recent"])
    for page in first["filings"].get("files", []):
        rows.extend(_rows(get_json(PAGE_URL.format(name=page["name"]))))
    return rows


def select_filings(
    wanted: list[tuple[int, int | None, str]], rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Pick the filing for each (fiscal year, quarter or None, form).

    Matches on the period the filing reports (reportDate), not when it was
    filed: Walmart's fiscal 2018 ends January 2018 and Adobe's 2015 ends
    November 2015, but each is identified by the year of its period end.
    A 10-Q also needs its quarter, taken from the period-end month.
    """
    picked: list[dict[str, str]] = []
    for year, quarter, form in wanted:
        for row in rows:
            report = row["reportDate"]
            if row["form"] != form or not report[:4].isdigit() or int(report[:4]) != year:
                continue
            if quarter is not None and (int(report[5:7]) + 2) // 3 != quarter:
                continue
            picked.append(row)
            break
    return picked

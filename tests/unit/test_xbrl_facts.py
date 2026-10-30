"""TDD: exact figures from SEC XBRL company facts. No network: a fixture holds the traps."""
from unittest.mock import patch

import pytest

from server.retrieval import xbrl_facts
from server.retrieval.xbrl_facts import (
    FactsError,
    display,
    find_fact,
    lookup,
    parse_period,
    resolve_metric,
    value_for_id,
)


def _flow(val, start, end, fy, fp, form, filed, accn="0000000001-24-000001"):
    return {"start": start, "end": end, "val": val, "fy": fy, "fp": fp, "form": form,
            "filed": filed, "accn": accn}


def _instant(val, end, fy, fp, form, filed, accn="0000000001-24-000001"):
    return {"end": end, "val": val, "fy": fy, "fp": fp, "form": form, "filed": filed,
            "accn": accn}


FACTS = {"facts": {"us-gaap": {
    # The FY2023 10-K repeats FY2022 and FY2021 as comparatives, all tagged fy=2023.
    "Revenues": {"label": "Revenues", "units": {"USD": [
        _flow(29_697_844_000, "2022-01-01", "2022-12-31", 2022, "FY", "10-K", "2023-01-27"),
        _flow(31_615_550_000, "2022-01-01", "2022-12-31", 2023, "FY", "10-K", "2024-01-26"),
        _flow(33_723_297_000, "2023-01-01", "2023-12-31", 2023, "FY", "10-K", "2024-01-26"),
        _flow(29_697_844_000, "2021-01-01", "2021-12-31", 2023, "FY", "10-K", "2024-01-26"),
        # A later amendment restates the year; the original filing wins.
        _flow(33_000_000_000, "2023-01-01", "2023-12-31", 2023, "FY", "10-K/A", "2024-06-01"),
        # Q3 10-Q: three months and nine months year-to-date.
        _flow(8_541_668_000, "2023-07-01", "2023-09-30", 2023, "Q3", "10-Q", "2023-10-20"),
        _flow(24_890_000_000, "2023-01-01", "2023-09-30", 2023, "Q3", "10-Q", "2023-10-20"),
    ]}},
    "Assets": {"label": "Assets", "units": {"USD": [
        _instant(48_594_768_000, "2022-12-31", 2023, "FY", "10-K", "2024-01-26"),
        _instant(48_731_992_000, "2023-12-31", 2023, "FY", "10-K", "2024-01-26"),
    ]}},
    # Cash flows: 10-Qs tag only year-to-date.
    "NetCashProvidedByUsedInOperatingActivities": {"label": "Operating cash", "units": {"USD": [
        _flow(7_274_301_000, "2023-01-01", "2023-12-31", 2023, "FY", "10-K", "2024-01-26"),
        _flow(5_000_000_000, "2023-01-01", "2023-09-30", 2023, "Q3", "10-Q", "2023-10-20"),
    ]}},
    "PaymentsToAcquirePropertyPlantAndEquipment": {"label": "Capex", "units": {"USD": [
        _flow(348_552_000, "2023-01-01", "2023-12-31", 2023, "FY", "10-K", "2024-01-26"),
    ]}},
    "EarningsPerShareDiluted": {"label": "EPS diluted", "units": {"USD/shares": [
        _flow(12.03, "2023-01-01", "2023-12-31", 2023, "FY", "10-K", "2024-01-26"),
    ]}},
    "StreamingMembershipsPaid": {"label": "Paid streaming memberships", "units": {"pure": []}},
}}}


@pytest.fixture(autouse=True)
def _no_network():
    with patch.object(xbrl_facts, "company_facts", return_value=FACTS), \
         patch.object(xbrl_facts, "cik_for", return_value=1065280):
        yield


@pytest.mark.parametrize("text, expected", [
    ("FY2023", (2023, "FY")), ("2023", (2023, "FY")), ("fiscal 2023", (2023, "FY")),
    ("fiscal year 2023", (2023, "FY")), ("FY23", (2023, "FY")), ("Q3 2023", (2023, "Q3")),
    ("Q3 FY2023", (2023, "Q3")), ("2023 Q3", (2023, "Q3")), ("q4-2025", (2025, "Q4")),
    ("latest", (None, "FY")), (None, (None, "FY")),
])
def test_parse_period(text, expected):
    assert parse_period(text) == expected


def test_unreadable_period_says_what_works():
    with pytest.raises(FactsError, match="Q3 2024"):
        parse_period("last summer")


def test_annual_value_is_the_filings_own_year_not_a_comparative():
    hit = find_fact(FACTS, "Revenues", 2023, "FY")
    assert hit["row"]["val"] == 33_723_297_000  # not 31.6B (FY2022 restated) nor the 10-K/A


def test_balance_sheet_value_is_the_year_end():
    assert find_fact(FACTS, "Assets", 2023, "FY")["row"]["val"] == 48_731_992_000


def test_quarter_prefers_three_months_over_year_to_date():
    assert find_fact(FACTS, "Revenues", 2023, "Q3")["row"]["val"] == 8_541_668_000


def test_quarter_falls_back_to_year_to_date_and_says_so():
    hit = find_fact(FACTS, "NetCashProvidedByUsedInOperatingActivities", 2023, "Q3")
    assert hit["row"]["val"] == 5_000_000_000
    assert "9 months year-to-date" in hit["note"]


def test_q4_is_full_year_minus_nine_months_and_labelled_derived():
    hit = find_fact(FACTS, "Revenues", 2023, "Q4")
    assert hit["row"]["val"] == 33_723_297_000 - 24_890_000_000
    assert hit["row"]["start"] == "2023-09-30"
    assert "minus nine months" in hit["derived"]


def test_q4_balance_sheet_value_is_the_year_end():
    assert find_fact(FACTS, "Assets", 2023, "Q4")["row"]["val"] == 48_731_992_000


@pytest.mark.parametrize("metric, name", [
    ("Revenue", "revenue"), ("net sales", "net sales"), ("Total revenues", "revenue"),
    ("CapEx", "capital expenditure"),
    ("Net PP&E", "property plant and equipment"), ("COGS", "cost of revenue"),
    ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquirePropertyPlantAndEquipment"),
    ("us-gaap:Assets", "Assets"),
])
def test_resolve_metric(metric, name):
    assert resolve_metric(metric)[0] == name


def test_lookup_returns_value_display_source_and_citation():
    entry = lookup("NFLX", "revenue", "FY2023")
    assert entry["value"] == 33_723_297_000
    assert entry["display"] == "$33,723.3 million"
    assert entry["citation"] == "[NFLX 10-K 2024-01-26]"
    assert entry["source"]["url"].endswith("/1065280/000000000124000001/")
    assert entry["period"] == {"fiscal_year": 2023, "fiscal_period": "FY",
                               "start": "2023-01-01", "end": "2023-12-31"}
    assert entry["id"] == "xbrl:NFLX:us-gaap:Revenues:FY2023"


def test_latest_means_the_newest_fiscal_year():
    assert lookup("NFLX", "revenue", "latest")["period"]["fiscal_year"] == 2023


def test_free_cash_flow_shows_its_formula():
    entry = lookup("NFLX", "free cash flow", "FY2023")
    assert entry["value"] == 7_274_301_000 - 348_552_000
    assert "minus capital expenditure" in entry["formula"]


def test_unknown_metric_suggests_concepts_the_company_reports():
    entry = lookup("NFLX", "paid memberships", "FY2023")
    assert "error" in entry
    assert entry["suggestions"][0]["concept"] == "us-gaap:StreamingMembershipsPaid"


def test_missing_year_lists_the_years_that_exist():
    entry = lookup("NFLX", "revenue", "FY2015")
    assert "no tagged revenue for FY2015" in entry["error"]
    assert "2023" in entry["error"]


def test_display_formats():
    assert display(-1_577_000_000, "USD") == "-$1,577.0 million"
    assert display(12.03, "USD/shares") == "$12.03 per share"
    assert display(443_000_000, "shares") == "443.0 million shares"


def test_fact_id_round_trips():
    assert value_for_id("xbrl:NFLX:us-gaap:Revenues:FY2023") == (33_723_297_000, "USD")
    assert value_for_id("xbrl:NFLX:us-gaap:Revenues:Q42023") == (8_833_297_000, "USD")
    assert value_for_id("chunk-123") is None


def test_net_sales_is_not_total_revenues():
    """Walmart Q4 FY2026: net sales 188,913 vs total revenues 190,656 (membership income)."""
    facts = {"facts": {"us-gaap": {
        "Revenues": {"label": "Revenues", "units": {"USD": [
            _flow(713_163, "2025-02-01", "2026-01-31", 2026, "FY", "10-K", "2026-03-13")]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"label": "Net sales", "units": {
            "USD": [_flow(706_000, "2025-02-01", "2026-01-31", 2026, "FY", "10-K", "2026-03-13")]}},
    }}}
    with patch.object(xbrl_facts, "company_facts", return_value=facts):
        assert lookup("WMT", "net sales", "FY2026")["value"] == 706_000
        assert lookup("WMT", "total revenue", "FY2026")["value"] == 713_163


@pytest.mark.parametrize("figure, grounded", [
    ("$33,723.3 million", True), ("$33,723 million", True), ("$33.7 billion", True),
    ("$33.72 billion", True), ("33,723,297,000", True), ("$34.7 billion", False),
    ("$33,700 million", False), ("$33.8 billion", False), ("$12.03", True), ("$12.04", False),
])
def test_figures_are_checked_against_facts_at_the_precision_written(figure, grounded):
    from server.retrieval.numerical_verifier import check_figures_against_values

    found, missing = check_figures_against_values(
        f"Revenue was {figure}.", [33_723_297_000, 12.03])
    assert (found == [figure]) is grounded
    assert (missing == [figure]) is not grounded

"""TDD: pull a company and a year window out of a natural-language question.

Live bug this exists for: "3M capital expenditure FY2018" returned "context
does not provide" -- all 28 MMM filings carry near-identical PP&E cash-flow
rows, and nothing tied "FY2018" to the 10-K filed 2019-02-07, so 2022-2023
look-alikes crowded it out of the top 5.
"""
from server.retrieval.query_filters import extract_filters, period_window


def test_company_name_maps_to_ticker():
    assert extract_filters("3M capital expenditure FY2018")["ticker"] == "MMM"


def test_uppercase_ticker_token_maps_to_ticker():
    assert extract_filters("What was NVDA revenue in 2025?")["ticker"] == "NVDA"


def test_multi_word_and_punctuated_names():
    assert extract_filters("Johnson & Johnson R&D spend 2022")["ticker"] == "JNJ"
    assert extract_filters("Lowe's net sales 2024")["ticker"] == "LOW"
    assert extract_filters("Coca-Cola dividends 2021")["ticker"] == "KO"


def test_single_letter_tickers_only_match_by_name():
    """A bare "F" or "V" or "T" in a question is far more likely to be an
    abbreviation than a ticker -- only the company name should count."""
    assert extract_filters("Ford revenue 2024")["ticker"] == "F"
    assert extract_filters("What is the F-score in 2024?")["ticker"] is None


def test_ambiguous_common_words_do_not_match():
    """"target", "block", "ups" are ordinary English -- a false company
    filter would hide the right answer, which is worse than no filter."""
    assert extract_filters("What is the target operating margin for 2024?")["ticker"] is None
    assert extract_filters("ups and downs in revenue 2023")["ticker"] is None


def test_two_companies_means_no_ticker_filter():
    """Comparisons need both companies' chunks; filtering to one would
    silently drop the other."""
    assert extract_filters("Compare Tesla and Ford gross margin 2024")["ticker"] is None


def test_unknown_company_means_no_ticker_filter():
    assert extract_filters("Acme Corp revenue 2020")["ticker"] is None


def test_fiscal_year_forms():
    assert extract_filters("3M capex FY2018")["years"] == (2018, 2018)
    assert extract_filters("3M capex FY 2018")["years"] == (2018, 2018)
    assert extract_filters("3M capex in fiscal year 2018")["years"] == (2018, 2018)
    assert extract_filters("3M capex FY18")["years"] == (2018, 2018)
    assert extract_filters("Q2 2022 revenue for Nike")["years"] == (2022, 2022)


def test_year_range_spans_all_mentioned_years():
    assert extract_filters("Nvidia revenue from 2023 to 2025")["years"] == (2023, 2025)


def test_no_year_means_no_year_filter():
    assert extract_filters("What is Apple's latest revenue?")["years"] is None


def test_numbers_that_are_not_years_are_ignored():
    assert extract_filters("3M capex of $1577 million")["years"] is None


def test_q4_question_prefers_the_annual_10k():
    """Live bug (2026-09-28, root-caused via evals/results/custom_answers.json):
    "AT&T total revenues in Q4 2025" retrieved and confidently cited a Q1 2026
    10-Q's prior-year comparative column instead of anything about Q4 2025 --
    the period_range filter alone let ANY filing dated in the 2025-2026 window
    through, 10-Qs included. Merck and Disney showed the identical pattern.
    Q4 is virtually never itself a separately-filed period -- it's read off
    the annual 10-K -- so a "Q4 <year>" question should only ever match 10-Ks."""
    assert extract_filters("What was AT&T total revenues in Q4 2025?")["filing_type"] == "10-K"
    assert extract_filters("Merck total revenues in Q4 2025")["filing_type"] == "10-K"


def test_q1_q2_q3_question_prefers_the_10q():
    assert extract_filters("Q2 2022 revenue for Nike")["filing_type"] == "10-Q"
    assert extract_filters("Q1 FY2026 Costco net sales")["filing_type"] == "10-Q"


def test_annual_or_fy_wording_without_a_quarter_prefers_the_10k():
    assert extract_filters("3M capex FY2018")["filing_type"] == "10-K"
    assert extract_filters("Apple full year revenue 2024")["filing_type"] == "10-K"


def test_no_period_wording_means_no_filing_type_filter():
    """A wrong filter hides the right answer -- same conservatism as the
    ticker/year filters. Don't guess when the question doesn't say."""
    assert extract_filters("What is Apple's latest revenue?")["filing_type"] is None
    assert extract_filters("Nvidia revenue from 2023 to 2025")["filing_type"] is None


def test_period_window_covers_both_fiscal_year_conventions():
    """Dec year-end (3M): FY2018 10-K filed 2019-02-07. Jan year-end
    (Walmart): FY2018 ended 2018-01-31, 10-K filed 2018-03. One window,
    Jan 1 of the first year through Dec 31 of the year after the last,
    covers both without knowing each company's fiscal calendar."""
    assert period_window((2018, 2018)) == ("2018-01-01", "2019-12-31")
    assert period_window((2023, 2025)) == ("2023-01-01", "2026-12-31")

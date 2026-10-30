"""Exact reported figures from SEC XBRL company facts, for any US-listed company.

Every 10-K and 10-Q carries its financial statements as tagged XBRL facts, and
SEC serves them per company at data.sec.gov (free, no key). Reading the tagged
value replaces the hardest part of passage search: finding one table row among
171,790 chunks and reading it out of read_html's column soup. Checked on
2026-10-30 against FinanceBench: 3M FY2018 capex 1,577, Amcor FY2020
receivables 1,615.9, Boeing FY2018 net PP&E 12,645, Microsoft FY2016 cost of
revenue 32,780, Nike FY2019 current assets 16,525, Netflix FY2023 revenue
33,723.3 (USD millions), all exact.

Traps this module handles:
- A 10-K for FY2023 also reports FY2022 and FY2021, all tagged fy=2023. The
  fact with the latest period end in that filing is the year asked for.
- Amendments restate. The original filing wins, as first filed.
- No filing reports Q4 on its own. A 10-K that tags a fourth-quarter figure is
  used; otherwise Q4 = full year minus nine months year-to-date, labelled as
  derived.
- 10-Q cash flow statements are year-to-date only. A quarter's value is the
  three-month figure when one exists, else the year-to-date figure, labelled.
"""
from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from typing import Any

import requests

from pipeline.edgar_client import SEC_USER_AGENT, get_cik_for_ticker

FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
FILING_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
NAMESPACES = ("us-gaap", "ifrs-full", "dei")
ANNUAL_FORMS = ("10-K", "20-F", "40-F")
QUARTER_FORMS = ("10-Q",)
UNIT_ORDER = ("USD", "USD/shares", "shares", "pure")


class FactsError(Exception):
    """A lookup failed for a reason the caller should be told verbatim."""


# Friendly name -> concepts, most specific first. A company uses one of them
# for a given year; revenue moved to the ASC 606 concepts in 2018.
METRICS: dict[str, tuple[str, ...]] = {
    "revenue": ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                "SalesRevenueGoodsNet", "RevenuesNetOfInterestExpense", "Revenue"),
    # Walmart's "Revenues" adds about $1.7B a quarter of membership income to net sales.
    "net sales": ("SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax",
                  "SalesRevenueGoodsNet", "Revenues"),
    "cost of revenue": ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold",
                        "CostOfServices", "CostOfSales"),
    "gross profit": ("GrossProfit",),
    "operating income": ("OperatingIncomeLoss", "ProfitLossFromOperatingActivities"),
    "net income": ("NetIncomeLoss", "ProfitLoss", "ProfitLossAttributableToOwnersOfParent"),
    "pretax income": (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "ProfitLossBeforeTax"),
    "income tax expense": ("IncomeTaxExpenseBenefit", "IncomeTaxExpenseContinuingOperations"),
    "interest expense": ("InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"),
    "research and development": ("ResearchAndDevelopmentExpense",
                                 "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"),
    "sg&a": ("SellingGeneralAndAdministrativeExpense",),
    "depreciation and amortization": ("DepreciationDepletionAndAmortization",
                                      "DepreciationAndAmortization",
                                      "DepreciationAmortizationAndAccretionNet",
                                      "DepreciationAmortizationAndOther", "Depreciation"),
    "eps basic": ("EarningsPerShareBasic",),
    "eps diluted": ("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"),
    "diluted shares": ("WeightedAverageNumberOfDilutedSharesOutstanding",),
    "basic shares": ("WeightedAverageNumberOfSharesOutstandingBasic",),
    "shares outstanding": ("CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding"),
    "operating cash flow": ("NetCashProvidedByUsedInOperatingActivities",
                            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
                            "CashFlowsFromUsedInOperatingActivities"),
    "capital expenditure": ("PaymentsToAcquirePropertyPlantAndEquipment",
                            "PaymentsToAcquireProductiveAssets",
                            "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"),
    "dividends paid": ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock",
                       "DividendsPaidClassifiedAsFinancingActivities"),
    "dividends per share": ("CommonStockDividendsPerShareDeclared",
                            "CommonStockDividendsPerShareCashPaid"),
    "share repurchases": ("PaymentsForRepurchaseOfCommonStock",),
    "total assets": ("Assets",),
    "current assets": ("AssetsCurrent", "CurrentAssets"),
    "total liabilities": ("Liabilities",),
    "current liabilities": ("LiabilitiesCurrent", "CurrentLiabilities"),
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "CashAndCashEquivalents",
             "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "accounts receivable": ("AccountsReceivableNetCurrent", "ReceivablesNetCurrent",
                            "TradeAndOtherCurrentReceivables"),
    "inventory": ("InventoryNet", "Inventories"),
    "accounts payable": ("AccountsPayableCurrent", "AccountsPayableTradeCurrent",
                         "TradeAndOtherCurrentPayables"),
    "property plant and equipment": ("PropertyPlantAndEquipmentNet", "PropertyPlantAndEquipment"),
    "goodwill": ("Goodwill",),
    "long-term debt": ("LongTermDebtNoncurrent", "LongTermDebt", "LongtermBorrowings"),
    "shareholders equity": ("StockholdersEquity",
                            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                            "Equity"),
}
ALIASES = {
    "sales": "net sales", "total revenue": "revenue",
    "revenues": "revenue", "total revenues": "revenue", "net revenue": "revenue",
    "cogs": "cost of revenue", "cost of goods sold": "cost of revenue",
    "cost of sales": "cost of revenue", "operating profit": "operating income",
    "ebit": "operating income", "net earnings": "net income", "net profit": "net income",
    "earnings per share": "eps diluted", "eps": "eps diluted", "diluted eps": "eps diluted",
    "capex": "capital expenditure", "capital expenditures": "capital expenditure",
    "purchases of property plant and equipment": "capital expenditure",
    "cash from operations": "operating cash flow",
    "cash flow from operations": "operating cash flow",
    "net cash from operating activities": "operating cash flow",
    "d&a": "depreciation and amortization", "r&d": "research and development",
    "selling general and administrative": "sg&a", "assets": "total assets",
    "liabilities": "total liabilities", "cash and cash equivalents": "cash",
    "receivables": "accounts receivable", "net receivables": "accounts receivable",
    "net ar": "accounts receivable", "ar": "accounts receivable",
    "inventories": "inventory", "payables": "accounts payable", "ap": "accounts payable",
    "pp&e": "property plant and equipment", "net pp&e": "property plant and equipment",
    "ppe": "property plant and equipment", "fixed assets": "property plant and equipment",
    "debt": "long-term debt", "long term debt": "long-term debt",
    "equity": "shareholders equity", "stockholders equity": "shareholders equity",
    "total equity": "shareholders equity", "buybacks": "share repurchases",
    "income before taxes": "pretax income", "tax expense": "income tax expense",
}
# Derived metrics: computed from two reported facts, formula returned with them.
DERIVED = {"free cash flow": ("operating cash flow", "capital expenditure")}

_PERIOD = re.compile(
    r"^(?:(?P<q1>q[1-4])\s*(?:fy|fiscal(?:\s+year)?)?\s*(?P<y1>\d{4})"
    r"|(?:fy|fiscal(?:\s+year)?)?\s*(?P<y2>\d{4})(?:\s*(?P<q2>q[1-4]))?"
    r"|fy\s*(?P<y3>\d{2}))$"
)


def parse_period(period: str | None) -> tuple[int | None, str]:
    """"FY2023", "2023", "fiscal 2023", "Q3 2024", "Q3 FY2024", "2024 Q3", "FY23", "latest".

    Returns (fiscal_year, "FY" | "Q1".."Q4"); fiscal_year None means the latest.
    """
    text = re.sub(r"[\s\-_]+", " ", (period or "latest").strip().lower())
    if text in ("", "latest"):
        return None, "FY"
    m = _PERIOD.match(text)
    if not m:
        raise FactsError(
            f"Period {period!r} not understood. Use a fiscal year like 'FY2023' or '2023', "
            "a quarter like 'Q3 2024', or 'latest'."
        )
    year = m["y1"] or m["y2"] or (f"20{m['y3']}" if m["y3"] else None)
    quarter = m["q1"] or m["q2"]
    return int(year), quarter.upper() if quarter else "FY"


@lru_cache(maxsize=4096)
def cik_for(ticker: str) -> int:
    try:
        return get_cik_for_ticker(ticker)
    except ValueError:
        raise FactsError(f"SEC has no company with ticker {ticker}.") from None


# ponytail: per-instance cache with no expiry (a warm Lambda can miss a filing
# made after it started); add a TTL if instances start living for days.
@lru_cache(maxsize=8)
def company_facts(cik: int) -> dict[str, Any]:
    """SEC's company facts JSON (2-6 MB), fetched once per warm instance."""
    for attempt in range(2):
        try:
            resp = requests.get(FACTS_URL.format(cik=cik),
                                headers={"User-Agent": SEC_USER_AGENT}, timeout=20)
        except requests.RequestException:
            if attempt:
                raise FactsError("SEC's data service did not respond; try again shortly.") from None
            continue
        if resp.status_code == 404:
            raise FactsError("SEC has no XBRL financial data for this company.")
        if resp.status_code == 200:
            return resp.json()
    raise FactsError(f"SEC's data service returned HTTP {resp.status_code}; try again shortly.")


def _days(row: dict[str, Any]) -> int:
    if "start" not in row:
        return 0
    return (date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])).days


def _rank(row: dict[str, Any]) -> tuple:
    """Latest period end first; among equals the original filing, first filed."""
    return (row["end"], not row["form"].endswith("/A"), _neg_date(row["filed"]))


def _neg_date(iso: str) -> int:
    return -date.fromisoformat(iso).toordinal()


def _pick(rows: list[dict[str, Any]], fy: int, fp: str, forms: tuple[str, ...],
          days: tuple[int, int] | None) -> dict[str, Any] | None:
    """The fact a filing for (fy, fp) reports for its own period. days=None: instant."""
    cands = [
        r for r in rows
        if r.get("fy") == fy and r.get("fp") == fp
        and r.get("form", "").split("/")[0] in forms
        and (("start" not in r) if days is None else (days[0] <= _days(r) <= days[1]))
    ]
    return max(cands, key=_rank) if cands else None


def _concept_rows(facts: dict[str, Any], concept: str) -> tuple[str, dict, str, list] | None:
    """(namespace, node, unit, rows) for a concept, preferring USD-like units."""
    for ns in NAMESPACES:
        node = facts.get("facts", {}).get(ns, {}).get(concept)
        if node and node.get("units"):
            units = node["units"]
            unit = next((u for u in UNIT_ORDER if u in units), next(iter(units)))
            return ns, node, unit, units[unit]
    return None


def _is_instant(rows: list[dict[str, Any]]) -> bool:
    return all("start" not in r for r in rows)


def find_fact(facts: dict[str, Any], concept: str, fy: int, fp: str) -> dict[str, Any] | None:
    """One concept's value for (fy, fp), or None. Adds "derived" when computed."""
    found = _concept_rows(facts, concept)
    if not found:
        return None
    ns, node, unit, rows = found
    instant = _is_instant(rows)
    base = {"concept": f"{ns}:{concept}", "label": node.get("label") or concept, "unit": unit}

    if fp == "FY":
        row = _pick(rows, fy, "FY", ANNUAL_FORMS, None if instant else (350, 380))
        return {**base, "row": row} if row else None
    if fp in ("Q1", "Q2", "Q3"):
        if instant:
            row = _pick(rows, fy, fp, QUARTER_FORMS, None)
            return {**base, "row": row} if row else None
        row = _pick(rows, fy, fp, QUARTER_FORMS, (80, 100))
        if row:
            return {**base, "row": row}
        ytd = _pick(rows, fy, fp, QUARTER_FORMS, (100, 290))
        if ytd:
            months = round(_days(ytd) / 30.4)
            return {**base, "row": ytd,
                    "note": f"No three-month figure is tagged; this is {months} months "
                            "year-to-date."}
        return None
    # Q4: balance-sheet items are the year-end value; flows are reported or derived.
    if instant:
        row = _pick(rows, fy, "FY", ANNUAL_FORMS, None)
        return {**base, "row": row} if row else None
    annual = _pick(rows, fy, "FY", ANNUAL_FORMS, (350, 380))
    if not annual:
        return None
    reported = [r for r in rows if r.get("fy") == fy and r.get("fp") == "FY"
                and 80 <= _days(r) <= 100 and r["end"] == annual["end"]]
    if reported:
        return {**base, "row": max(reported, key=_rank)}
    nine = _pick(rows, fy, "Q3", QUARTER_FORMS, (250, 290))
    if not nine:
        return None
    row = {**annual, "val": annual["val"] - nine["val"], "start": nine["end"]}
    return {**base, "row": row,
            "derived": f"full year to {annual['end']} ({annual['val']:,}) minus nine months "
                       f"to {nine['end']} ({nine['val']:,}), from the {annual['form']} filed "
                       f"{annual['filed']} and the 10-Q filed {nine['filed']}"}


def latest_fiscal_year(facts: dict[str, Any], concepts: tuple[str, ...]) -> int | None:
    years = [
        r["fy"] for c in concepts if (found := _concept_rows(facts, c))
        for r in found[3] if r.get("fp") == "FY" and r.get("fy")
    ]
    return max(years) if years else None


def display(value: float, unit: str) -> str:
    """How a filing would print it: "$33,723.3 million", "$2.45 per share"."""
    if unit == "USD":
        sign = "-" if value < 0 else ""
        v = abs(value)
        if v >= 1e6:
            return f"{sign}${v / 1e6:,.1f} million"
        return f"{sign}${v:,.0f}"
    if unit == "USD/shares":
        return f"${value:,.2f} per share"
    if unit == "shares":
        return f"{value / 1e6:,.1f} million shares" if abs(value) >= 1e6 else f"{value:,.0f} shares"
    return f"{value:,}"


def fact_id(ticker: str, concept: str, fy: int, fp: str) -> str:
    return f"xbrl:{ticker}:{concept}:{fp}{fy}"


def _normalize(metric: str) -> str:
    text = re.sub(r"[^a-z0-9&+ ]+", " ", metric.lower().replace("-", " "))
    return re.sub(r"\s+", " ", text).strip()


def resolve_metric(metric: str) -> tuple[str, tuple[str, ...]]:
    """(canonical name, candidate concepts). An XBRL concept name is used as given."""
    raw = metric.strip()
    name = _normalize(raw)
    name = ALIASES.get(name, name)
    keyed = {_normalize(k): k for k in METRICS}
    if name in keyed:  # before the concept test: "Revenue" and "COGS" look like concepts
        key = keyed[name]
        return key, METRICS[key]
    if name in DERIVED:
        return name, ()
    concept = raw.split(":", 1)[1] if ":" in raw else raw
    if re.fullmatch(r"[A-Z][A-Za-z0-9]+", concept):
        return concept, (concept,)
    return name, ()


def suggest(facts: dict[str, Any], metric: str, limit: int = 8) -> list[dict[str, str]]:
    """Concepts this company reports whose name or label shares the metric's words."""
    words = {w for w in _normalize(metric).split() if len(w) > 2}
    scored = []
    for ns in NAMESPACES:
        for concept, node in facts.get("facts", {}).get(ns, {}).items():
            spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", concept)
            text = f"{spaced} {node.get('label') or ''}".lower()
            hits = sum(w in text for w in words)
            if hits:
                label = node.get("label") or concept
                scored.append((hits, -len(concept), f"{ns}:{concept}", label))
    scored.sort(reverse=True)
    return [{"concept": c, "label": label} for _, _, c, label in scored[:limit]]


def lookup(ticker: str, metric: str, period: str | None) -> dict[str, Any]:
    """One metric for one company and period, as a result entry for the tools."""
    fy, fp = parse_period(period)
    cik = cik_for(ticker)
    facts = company_facts(cik)
    name, concepts = resolve_metric(metric)

    if name in DERIVED:
        parts = [lookup(ticker, part, period) for part in DERIVED[name]]
        if any("error" in p for p in parts):
            return {"metric": metric, "error": "; ".join(p["error"] for p in parts if "error" in p)}
        ocf, capex = parts
        value = ocf["value"] - abs(capex["value"])
        return {"metric": metric, "value": value, "unit": "USD", "display": display(value, "USD"),
                "period": ocf["period"],
                "formula": f"operating cash flow {ocf['display']} minus capital expenditure "
                           f"{capex['display']}",
                "inputs": parts, "citation": ocf["citation"]}

    if not concepts:
        return {"metric": metric,
                "error": f"{metric!r} is not a metric name FinRAG knows. Pass one of the "
                         "suggested concepts as the metric, or a common name such as "
                         "'revenue' or 'capital expenditure'.",
                "suggestions": suggest(facts, metric)}

    year = fy or latest_fiscal_year(facts, concepts)
    if year is None:
        return {"metric": metric, "error": f"{ticker} reports no annual {name} in XBRL.",
                "suggestions": suggest(facts, metric)}
    for concept in concepts:
        hit = find_fact(facts, concept, year, fp)
        if hit:
            row = hit["row"]
            accession = row["accn"].replace("-", "")
            entry = {
                "metric": metric, "concept": hit["concept"], "label": hit["label"],
                "value": row["val"], "unit": hit["unit"],
                "display": display(row["val"], hit["unit"]),
                "period": {"fiscal_year": year, "fiscal_period": fp,
                           "start": row.get("start"), "end": row["end"]},
                "source": {"form": row["form"], "filed": row["filed"], "accession": row["accn"],
                           "url": FILING_URL.format(cik=cik, accession=accession)},
                "citation": f"[{ticker} {row['form']} {row['filed']}]",
                "id": fact_id(ticker, hit["concept"], year, fp),
            }
            for key in ("derived", "note"):
                if hit.get(key):
                    entry[key] = hit[key]
            return entry
    years = sorted({r["fy"] for c in concepts if (f := _concept_rows(facts, c))
                    for r in f[3] if r.get("fy")}, reverse=True)[:8]
    label = f"{fp} {year}" if fp != "FY" else f"FY{year}"
    return {"metric": metric,
            "error": f"{ticker} has no tagged {name} for {label}."
                     + (f" Fiscal years with data: {years}." if years else ""),
            "suggestions": suggest(facts, metric) if not years else []}


def value_for_id(fid: str) -> tuple[float, str] | None:
    """(value, unit) for an id from lookup(), recomputed; None if it does not resolve."""
    m = re.fullmatch(r"xbrl:([A-Z][A-Z.\-]{0,5}):([\w-]+:\w+):(FY|Q[1-4])(\d{4})", fid)
    if not m:
        return None
    ticker, concept, fp, fy = m.groups()
    try:
        hit = find_fact(company_facts(cik_for(ticker)), concept.split(":", 1)[1], int(fy), fp)
    except FactsError:
        return None
    return (hit["row"]["val"], hit["unit"]) if hit else None

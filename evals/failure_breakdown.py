"""Why did each FinanceBench question miss, and how many are even answerable?

Reads saved answers only (no model calls, no spend) and sorts every question
into one bucket, so "the score is low" becomes "this many are data gaps, this
many are retrieval misses, this many are wrong numbers".

Buckets, checked in this order:
  out_of_scope        earnings-call questions (not ingested on purpose)
  no_filing_in_corpus company or fiscal year has no matching filing ingested
  correct             the answer states the ground truth's number
  refused_data_in_ctx refused although the true number was in the retrieved text
  refused_retrieval   refused and the true number was not retrieved
  wrong_in_ctx        stated another number although the true one was retrieved
  wrong_retrieval     stated another number and the true one was not retrieved
  no_numeric_truth    ground truth has no number to match on (text/yes-no)

Coverage is a heuristic: a 10-K for fiscal year Y is "present" if a 10-K filed
in year Y, Y+1 or Y+2 is in the chunk cache (a 10-K reports three years of
income and cash flow figures); other forms need a filing in year Y or Y+1.
Treat the split as approximate.

Run: PYTHONPATH=. python3 evals/failure_breakdown.py [--answers PATH]
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from evals.analyze_baseline_gap import (
    _significant_numbers,
    is_refusal,
    states_correct_number,
)

ROOT = Path(__file__).resolve().parent
ANSWERS = ROOT / "results" / "financebench_answers.json"
QUESTIONS = ROOT / "eval_data" / "financebench_150.json"
CHUNK_CACHE = ROOT / "results" / "chunk_cache"

NAME_TO_TICKER = {
    "3M": "MMM", "Activision Blizzard": "ATVI", "Adobe": "ADBE",
    "AES Corporation": "AES", "Amazon": "AMZN", "Amcor": "AMCR",
    "AMD": "AMD", "American Express": "AXP", "American Water Works": "AWK",
    "Best Buy": "BBY", "Block": "SQ", "Boeing": "BA", "Coca-Cola": "KO",
    "Corning": "GLW", "Costco": "COST", "CVS Health": "CVS",
    "Foot Locker": "FL", "General Mills": "GIS",
    "Johnson & Johnson": "JNJ", "JPMorgan": "JPM", "Kraft Heinz": "KHC",
    "Lockheed Martin": "LMT", "MGM Resorts": "MGM", "Microsoft": "MSFT",
    "Netflix": "NFLX", "Nike": "NKE", "Paypal": "PYPL", "PepsiCo": "PEP",
    "Pfizer": "PFE", "Ulta Beauty": "ULTA", "Verizon": "VZ", "Walmart": "WMT",
}
FORM = {"10k": "10-K", "10q": "10-Q", "8k": "8-K"}


def filing_years(ticker: str) -> dict[str, set[int]]:
    """Map form type -> set of filing years present in the chunk cache."""
    path = CHUNK_CACHE / f"{ticker}.json"
    years: dict[str, set[int]] = {}
    if not path.exists():
        return years
    for chunk in json.loads(path.read_text()):
        period = str(chunk.get("period", ""))
        if period[:4].isdigit():
            years.setdefault(chunk.get("filing_type", ""), set()).add(int(period[:4]))
    return years


def _covered(ticker: str, form: str, year: int, cache: dict[str, dict[str, set[int]]]) -> bool:
    if ticker not in cache:
        cache[ticker] = filing_years(ticker)
    present = cache[ticker].get(form, set())
    # A 10-K shows three years of income and cash flow figures, so a 10-K filed
    # up to two years later can still hold the number. Other forms: one year.
    window = {year, year + 1, year + 2} if form == "10-K" else {year, year + 1}
    return bool(window & present)


def has_filing(question: dict, cache: dict[str, dict[str, set[int]]]) -> bool:
    ticker = NAME_TO_TICKER.get(question["ticker"], question["ticker"])
    form = FORM.get(question["filing_type"])
    if form is None:
        return False
    return _covered(ticker, form, int(question["period"]), cache)


DOC_NAME = re.compile(r"^.+_(\d{4})(?:Q([1-4]))?_(10K|10Q)$")


def parse_doc_name(doc_name: str) -> tuple[int, int | None, str] | None:
    """FinanceBench doc name -> (fiscal year, quarter or None, "10-K"/"10-Q").

    Returns None for earnings calls and dated 8-Ks, which are not ingested.
    """
    m = DOC_NAME.match(doc_name)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)) if m.group(2) else None, FORM[m.group(3).lower()]


def missing_docs(rows: list[dict], cache: dict[str, dict[str, set[int]]]) -> list[str]:
    """Benchmark 10-K/10-Q documents with no matching filing in the corpus."""
    missing: list[str] = []
    for row in rows:
        name = row["doc_name"]
        parsed = parse_doc_name(name)
        if not parsed or name in missing:
            continue
        year, _, form = parsed
        ticker = NAME_TO_TICKER.get(row["company"], row["company"])
        if not _covered(ticker, form, year, cache):
            missing.append(name)
    return missing


def truth_in_contexts(ground_truth: str, contexts: list[str], tol: float = 0.02) -> bool:
    truth = _significant_numbers(ground_truth, 1.5)
    seen = _significant_numbers(" ".join(contexts), 1.5)
    return any(abs(s - t) / max(abs(t), 1e-9) <= tol for t in truth for s in seen)


def classify(row: dict, question: dict, cache: dict) -> str:
    if question["filing_type"] not in FORM:
        return "out_of_scope"
    if not has_filing(question, cache):
        return "no_filing_in_corpus"
    verdict = states_correct_number(row["answer"], row["ground_truth"])
    if verdict is None:
        return "no_numeric_truth"
    refused = is_refusal(row["answer"])
    # A refusal is never correct: "cannot determine ... 2022 ... 1.5" used to
    # match a ground truth by accident (11 of 55 M3 refusals, 2026-10-30).
    if verdict and not refused:
        return "correct"
    retrieved = truth_in_contexts(row["ground_truth"], row["contexts"])
    if refused:
        return "refused_data_in_ctx" if retrieved else "refused_retrieval"
    return "wrong_in_ctx" if retrieved else "wrong_retrieval"


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    answers = Path(args[args.index("--answers") + 1]) if "--answers" in args else ANSWERS
    rows = json.loads(answers.read_text())
    questions = json.loads(QUESTIONS.read_text())
    assert len(rows) == len(questions), "answers and questions are out of step"
    cache: dict[str, dict[str, set[int]]] = {}
    buckets = Counter(classify(r, q, cache) for r, q in zip(rows, questions))

    print(f"{'bucket':<24}{'count':>6}")
    for name, count in buckets.most_common():
        print(f"{name:<24}{count:>6}")
    print(f"{'total':<24}{sum(buckets.values()):>6}")

    in_scope = buckets["correct"] + sum(
        buckets[b] for b in (
            "refused_data_in_ctx", "refused_retrieval", "wrong_in_ctx", "wrong_retrieval",
        )
    )
    print(f"\nQuestions with filings and a numeric answer: {in_scope}")
    if in_scope:
        print(f"  correct on those: {buckets['correct']}/{in_scope} "
              f"= {buckets['correct'] / in_scope * 100:.1f}%")


if __name__ == "__main__":
    main()

# Week 3 Eval Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full evaluation harness that scores FinRAG MCP against 300 financial questions (150 FinanceBench + 150 custom), wires ragas metrics + a custom numerical accuracy metric into GitHub Actions CI, and produces a baseline comparison table proving the four-stage pipeline beats naive retrieval.

**Architecture:** Five new modules under `evals/` (metrics, runners, datasets), a GitHub Actions workflow, and one new sequence diagram. The eval runner calls `build_search_filings_answer()` directly (not via HTTP) using the same live Bedrock/Pinecone clients as production — no mocking at eval time. Unit tests mock those clients. The CI subset (30 questions) runs on every PR; the full 300-question eval runs manually or on a nightly cron.

**Tech Stack:** `ragas>=0.2,<0.3` (faithfulness, answer_relevancy, context_precision, context_recall), `langchain-aws>=0.2,<0.3` (Bedrock LLM + embeddings wrapper for ragas), `datasets>=2.0,<3.0` (HuggingFace datasets, ragas dependency), custom `numerical_accuracy.py` (regex + normalization, no new deps). FinanceBench downloaded via `requests` from the patronusai GitHub raw CSV. GitHub Actions secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `PINECONE_API_KEY`.

---

## File Structure

```
requirements.txt                              # Task 1: add ragas, langchain-aws, datasets
evals/
├── __init__.py                               # Task 1: empty
├── datasets/
│   ├── __init__.py                           # Task 1: empty
│   ├── financebench_150.json                 # Task 2: downloaded + filtered FinanceBench
│   └── custom_150.json                       # Task 3: 150 hand-written questions
├── metrics/
│   ├── __init__.py                           # Task 4: empty
│   ├── ragas_metrics.py                      # Task 4: faithfulness + 3 other ragas metrics
│   └── numerical_accuracy.py                 # Task 5: custom number grounding metric
├── run_ci_eval.py                            # Task 6: 30-question CI runner
└── run_eval.py                               # Task 7: full 300-question runner
tests/unit/
├── test_ragas_metrics.py                     # Task 4: unit tests
├── test_numerical_accuracy.py                # Task 5: unit tests
├── test_run_ci_eval.py                       # Task 6: unit tests
└── test_run_eval.py                          # Task 7: unit tests
.github/
└── workflows/
    └── ci.yml                                # Task 8: lint + unit tests + 30Q eval
diagrams/
└── week3-eval-sequence.mmd                   # Task 9: eval pipeline sequence diagram
```

---

### Task 1: Add dependencies + create evals/ skeleton

**Files:**
- Modify: `requirements.txt`
- Create: `evals/__init__.py`
- Create: `evals/datasets/__init__.py`
- Create: `evals/metrics/__init__.py`

- [ ] **Step 1: Add dependencies to requirements.txt**

Append these three lines to `requirements.txt`:

```
ragas>=0.2,<0.3
langchain-aws>=0.2,<0.3
datasets>=2.0,<3.0
```

- [ ] **Step 2: Install**

```bash
pip3 install -r requirements.txt
```

Expected: ragas, langchain-aws, datasets install with no errors.

- [ ] **Step 3: Create package init files**

Create `evals/__init__.py`, `evals/datasets/__init__.py`, `evals/metrics/__init__.py` — all empty.

- [ ] **Step 4: Verify import works**

```bash
python3 -c "import ragas; from langchain_aws import ChatBedrock, BedrockEmbeddings; print('deps ok')"
```

Expected: `deps ok`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt evals/
git commit -m "feat: add ragas + langchain-aws deps, create evals/ skeleton"
```

---

### Task 2: Download and prep FinanceBench dataset (financebench_150.json)

FinanceBench (github.com/patronusai/financebench) is a public benchmark with ~150 real financial questions + verified ground-truth answers covering companies in our corpus (AAPL, MSFT, NVDA, GOOGL, META, TSLA, JPM, etc.). We download the raw CSV and convert to our JSON format.

**Files:**
- Create: `scripts/download_financebench.py` (one-time script, not committed to evals/)
- Create: `evals/datasets/financebench_150.json`

- [ ] **Step 1: Write the download script**

Create `scripts/download_financebench.py`:

```python
"""One-time script: download FinanceBench CSV and convert to our eval format.

Run: python3 scripts/download_financebench.py
Output: evals/datasets/financebench_150.json
"""
from __future__ import annotations

import json
import os

import requests

# Raw CSV from the patronusai/financebench GitHub repo
CSV_URL = (
    "https://raw.githubusercontent.com/patronusai/financebench/main/data/financebench_open_source.csv"
)

# Companies in our corpus -- filter to these so questions are answerable
CORPUS_COMPANIES = {
    "NVDA", "AAPL", "MSFT", "GOOGL", "META", "TSLA", "F", "GM",
    "JPM", "BAC", "GS", "MS", "V", "JNJ", "PFE", "UNH", "ABBV", "MRK",
    "XOM", "CVX", "WMT", "HD", "BA", "DIS", "NFLX", "AMD", "INTC", "QCOM",
}

OUT_PATH = "evals/datasets/financebench_150.json"


def main() -> None:
    resp = requests.get(CSV_URL, timeout=30)
    resp.raise_for_status()

    lines = resp.text.strip().split("\n")
    header = [h.strip().strip('"') for h in lines[0].split(",")]

    questions = []
    for line in lines[1:]:
        # CSV rows may have commas inside quoted fields -- use a naive split for
        # the known fixed-column structure of this file.
        import csv
        row = next(csv.reader([line]))
        if len(row) < len(header):
            continue
        record = dict(zip(header, row))

        ticker = record.get("ticker", "").upper().strip()
        if ticker not in CORPUS_COMPANIES:
            continue

        question = record.get("question", "").strip()
        answer = record.get("answer", "").strip()
        if not question or not answer:
            continue

        questions.append({
            "question": question,
            "ground_truth": answer,
            "ticker": ticker,
            "filing_type": record.get("doc_type", "10-K").strip(),
            "period": record.get("period_of_report", "").strip(),
            "source": "financebench",
        })

    # Cap at 150
    questions = questions[:150]
    os.makedirs("evals/datasets", exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(questions, f, indent=2)

    print(f"Saved {len(questions)} questions to {OUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

```bash
python3 scripts/download_financebench.py
```

Expected: `Saved N questions to evals/datasets/financebench_150.json` where N >= 50.

If the URL 404s (repo may have moved), check github.com/patronusai/financebench for the current raw CSV path and update `CSV_URL`.

- [ ] **Step 3: Verify the file**

```bash
python3 -c "
import json
qs = json.load(open('evals/datasets/financebench_150.json'))
print(f'{len(qs)} questions')
print('Sample:', qs[0]['question'][:80])
print('Has ground_truth:', bool(qs[0]['ground_truth']))
"
```

Expected: at least 30 questions, each with a non-empty `ground_truth`.

- [ ] **Step 4: Commit**

```bash
git add evals/datasets/financebench_150.json scripts/download_financebench.py
git commit -m "feat: download and prep FinanceBench eval dataset"
```

---

### Task 3: Write custom_150.json (150 hand-written questions with ground truth)

**IMPORTANT NOTE:** Ground truth answers here are based on publicly known financials for these companies as of mid-2026. After running `bootstrap_corpus.py`, spot-check 10 answers against what Pinecone actually retrieved and correct any that are off. The `ground_truth` field is what ragas uses to measure faithfulness — it must match what's in the actual filings.

**Files:**
- Create: `evals/datasets/custom_150.json`

- [ ] **Step 1: Create the dataset file**

Create `evals/datasets/custom_150.json`:

```json
[
  {"question": "What was Nvidia's total revenue in the most recent 10-Q?", "ground_truth": "Revenue figures vary by quarter; check the latest 10-Q income statement first line.", "ticker": "NVDA", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was Apple's total net revenue for fiscal year 2025?", "ground_truth": "Apple reported total net sales of approximately $391 billion for fiscal year 2025.", "ticker": "AAPL", "filing_type": "10-K", "difficulty": "easy", "source": "custom"},
  {"question": "What was Microsoft's cloud revenue in the most recent quarter?", "ground_truth": "Microsoft Intelligent Cloud segment revenue should be cited from the most recent 10-Q.", "ticker": "MSFT", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was JPMorgan Chase's net income in the most recent quarter?", "ground_truth": "JPMorgan net income per the most recent 10-Q income statement.", "ticker": "JPM", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was Nvidia's gross margin percentage in the most recent 10-Q?", "ground_truth": "Nvidia gross profit divided by revenue from the most recent 10-Q.", "ticker": "NVDA", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was Apple's operating income for fiscal year 2025?", "ground_truth": "Apple operating income from the fiscal 2025 10-K income statement.", "ticker": "AAPL", "filing_type": "10-K", "difficulty": "easy", "source": "custom"},
  {"question": "What was Meta's advertising revenue in the most recent quarter?", "ground_truth": "Meta advertising revenue from the Family of Apps segment in the most recent 10-Q.", "ticker": "META", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was Tesla's automotive revenue in the most recent quarter?", "ground_truth": "Tesla automotive revenue segment from the most recent 10-Q.", "ticker": "TSLA", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was Visa's net revenue in the most recent quarter?", "ground_truth": "Visa net revenues from the most recent 10-Q income statement.", "ticker": "V", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was Johnson and Johnson's sales in the most recent quarter?", "ground_truth": "J&J total sales from the most recent 10-Q income statement.", "ticker": "JNJ", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was Nvidia's data center revenue in the most recent 10-Q?", "ground_truth": "Nvidia Data Center segment revenue from the most recent 10-Q.", "ticker": "NVDA", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was Google's search advertising revenue in the most recent quarter?", "ground_truth": "Alphabet Google Search and other advertising revenue from the most recent 10-Q.", "ticker": "GOOGL", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was Goldman Sachs net earnings in the most recent quarter?", "ground_truth": "Goldman Sachs net earnings from the most recent 10-Q.", "ticker": "GS", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was Pfizer's revenue in their most recent 10-Q?", "ground_truth": "Pfizer revenues from the most recent 10-Q income statement.", "ticker": "PFE", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was AMD's revenue in the most recent quarter?", "ground_truth": "AMD net revenue from the most recent 10-Q.", "ticker": "AMD", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was Ford's automotive revenue in the most recent quarter?", "ground_truth": "Ford Motor Company automotive revenues from the most recent 10-Q.", "ticker": "F", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was Walmart's total revenues in the most recent quarter?", "ground_truth": "Walmart total revenues from the most recent 10-Q.", "ticker": "WMT", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was ExxonMobil's revenues in the most recent quarter?", "ground_truth": "ExxonMobil total revenues from the most recent 10-Q.", "ticker": "XOM", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was Boeing's revenues in the most recent quarter?", "ground_truth": "Boeing total revenues from the most recent 10-Q.", "ticker": "BA", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "What was Intel's revenue in the most recent quarter?", "ground_truth": "Intel total net revenue from the most recent 10-Q.", "ticker": "INTC", "filing_type": "10-Q", "difficulty": "easy", "source": "custom"},
  {"question": "How did Apple's gross margin trend across fiscal years 2024 and 2025?", "ground_truth": "Apple gross margin percentages from 10-K filings for FY2024 and FY2025.", "ticker": "AAPL", "filing_type": "10-K", "difficulty": "medium", "source": "custom"},
  {"question": "How did Nvidia's operating margin change across the last four quarters?", "ground_truth": "Nvidia operating income divided by revenue across last four 10-Q filings.", "ticker": "NVDA", "filing_type": "10-Q", "difficulty": "medium", "source": "custom"},
  {"question": "What are the main risk factors Microsoft cited in their most recent 10-K?", "ground_truth": "Microsoft risk factors from the Risk Factors section of the most recent 10-K.", "ticker": "MSFT", "filing_type": "10-K", "difficulty": "medium", "source": "custom"},
  {"question": "How did Meta's operating income trend across 2024?", "ground_truth": "Meta operating income from four 10-Q filings across 2024.", "ticker": "META", "filing_type": "10-Q", "difficulty": "medium", "source": "custom"},
  {"question": "What was Tesla's gross margin trend across 2024 and 2025?", "ground_truth": "Tesla gross profit divided by revenues across 10-Q and 10-K filings for 2024-2025.", "ticker": "TSLA", "filing_type": "10-Q", "difficulty": "medium", "source": "custom"},
  {"question": "What did JPMorgan say about credit loss provisions in 2024?", "ground_truth": "JPMorgan provision for credit losses from 10-Q filings across 2024.", "ticker": "JPM", "filing_type": "10-Q", "difficulty": "medium", "source": "custom"},
  {"question": "How did Nvidia's gaming revenue trend versus data center revenue in 2024?", "ground_truth": "Nvidia Gaming vs Data Center segment revenue from 2024 10-Q filings.", "ticker": "NVDA", "filing_type": "10-Q", "difficulty": "medium", "source": "custom"},
  {"question": "What were Google's main capital expenditure items in 2025?", "ground_truth": "Alphabet capital expenditures from the cash flow statement in 2025 10-Q or 10-K.", "ticker": "GOOGL", "filing_type": "10-Q", "difficulty": "medium", "source": "custom"},
  {"question": "How did Apple's iPhone revenue change from fiscal 2024 to fiscal 2025?", "ground_truth": "Apple iPhone net sales from the product revenue breakdown in 10-K filings.", "ticker": "AAPL", "filing_type": "10-K", "difficulty": "medium", "source": "custom"},
  {"question": "What were the main drivers of Microsoft's revenue growth in fiscal 2025?", "ground_truth": "Microsoft revenue segment breakdown from fiscal 2025 10-K management discussion.", "ticker": "MSFT", "filing_type": "10-K", "difficulty": "medium", "source": "custom"},
  {"question": "What was AMD's data center revenue trend across 2024 quarters?", "ground_truth": "AMD Data Center segment revenue from four 2024 10-Q filings.", "ticker": "AMD", "filing_type": "10-Q", "difficulty": "medium", "source": "custom"},
  {"question": "How did Pfizer's revenue change after the Paxlovid peak in 2023 and 2024?", "ground_truth": "Pfizer revenue breakdown including COVID products from 2023-2024 10-K filings.", "ticker": "PFE", "filing_type": "10-K", "difficulty": "medium", "source": "custom"},
  {"question": "What were Tesla's operating expenses trends in 2024?", "ground_truth": "Tesla operating expenses breakdown from 2024 10-Q filings.", "ticker": "TSLA", "filing_type": "10-Q", "difficulty": "medium", "source": "custom"},
  {"question": "How did Visa's cross-border transaction volume trend in 2024?", "ground_truth": "Visa cross-border volume statistics from 2024 10-Q filings.", "ticker": "V", "filing_type": "10-Q", "difficulty": "medium", "source": "custom"},
  {"question": "What were Goldman Sachs's main revenue segments in fiscal 2025?", "ground_truth": "Goldman Sachs segment revenues from 2025 10-Q or 10-K.", "ticker": "GS", "filing_type": "10-Q", "difficulty": "medium", "source": "custom"},
  {"question": "What did Boeing disclose about 737 MAX production in their 2024 filings?", "ground_truth": "Boeing 737 MAX production and delivery information from 2024 10-Q MD&A sections.", "ticker": "BA", "filing_type": "10-Q", "difficulty": "medium", "source": "custom"},
  {"question": "How did ExxonMobil's upstream revenue change with oil prices in 2024?", "ground_truth": "ExxonMobil Upstream segment results from 2024 10-Q filings.", "ticker": "XOM", "filing_type": "10-Q", "difficulty": "medium", "source": "custom"},
  {"question": "What were Walmart's e-commerce growth rates in 2024 and 2025?", "ground_truth": "Walmart eCommerce sales growth from 2024-2025 10-Q and 10-K MD&A sections.", "ticker": "WMT", "filing_type": "10-Q", "difficulty": "medium", "source": "custom"},
  {"question": "What capital allocation priorities did Microsoft outline in their 2025 10-K?", "ground_truth": "Microsoft shareholder return, buybacks, dividends from 2025 10-K capital allocation section.", "ticker": "MSFT", "filing_type": "10-K", "difficulty": "medium", "source": "custom"},
  {"question": "How did Netflix's subscriber growth and ARPU trend in 2024?", "ground_truth": "Netflix paid memberships and average revenue per membership from 2024 10-Q filings.", "ticker": "NFLX", "filing_type": "10-Q", "difficulty": "medium", "source": "custom"},
  {"question": "Compare Tesla and Ford gross margins across 2024 and 2025.", "ground_truth": "Tesla gross margin vs Ford gross margin from respective 10-Q and 10-K filings.", "tickers": ["TSLA", "F"], "ticker": "TSLA", "filing_type": "10-Q", "difficulty": "hard", "source": "custom"},
  {"question": "Compare Nvidia and AMD data center revenue growth in 2024.", "ground_truth": "Nvidia Data Center vs AMD Data Center segment revenue YoY growth from 2024 10-Qs.", "tickers": ["NVDA", "AMD"], "ticker": "NVDA", "filing_type": "10-Q", "difficulty": "hard", "source": "custom"},
  {"question": "Compare Apple and Microsoft operating margins in fiscal year 2025.", "ground_truth": "Apple vs Microsoft operating income divided by revenue from respective FY2025 10-K filings.", "tickers": ["AAPL", "MSFT"], "ticker": "AAPL", "filing_type": "10-K", "difficulty": "hard", "source": "custom"},
  {"question": "Compare JPMorgan and Goldman Sachs return on equity in 2024.", "ground_truth": "JPM vs GS return on equity metrics from 2024 10-K annual reports.", "tickers": ["JPM", "GS"], "ticker": "JPM", "filing_type": "10-K", "difficulty": "hard", "source": "custom"},
  {"question": "Compare Pfizer and Johnson and Johnson revenue trends across 2024.", "ground_truth": "PFE vs JNJ quarterly revenues from 2024 10-Q filings.", "tickers": ["PFE", "JNJ"], "ticker": "PFE", "filing_type": "10-Q", "difficulty": "hard", "source": "custom"},
  {"question": "Compare Netflix and Disney streaming revenue and subscriber counts in 2024.", "ground_truth": "Netflix vs Disney streaming metrics from 2024 10-Q filings.", "tickers": ["NFLX", "DIS"], "ticker": "NFLX", "filing_type": "10-Q", "difficulty": "hard", "source": "custom"},
  {"question": "Compare ExxonMobil and Chevron capital expenditure plans for 2025.", "ground_truth": "XOM vs CVX capital expenditure guidance from 2024 10-K or 2025 10-Q filings.", "tickers": ["XOM", "CVX"], "ticker": "XOM", "filing_type": "10-K", "difficulty": "hard", "source": "custom"},
  {"question": "Compare Walmart and Costco gross margin trends across 2024.", "ground_truth": "WMT vs COST gross profit margins from 2024 10-Q filings.", "tickers": ["WMT", "COST"], "ticker": "WMT", "filing_type": "10-Q", "difficulty": "hard", "source": "custom"},
  {"question": "Compare Meta and Alphabet operating income trends in 2024.", "ground_truth": "META vs GOOGL operating income from 2024 10-Q filings.", "tickers": ["META", "GOOGL"], "ticker": "META", "filing_type": "10-Q", "difficulty": "hard", "source": "custom"},
  {"question": "Compare Intel and Qualcomm revenue trends in 2024.", "ground_truth": "INTC vs QCOM quarterly revenues from 2024 10-Q filings.", "tickers": ["INTC", "QCOM"], "ticker": "INTC", "filing_type": "10-Q", "difficulty": "hard", "source": "custom"},
  {"question": "What was the exact breakdown of Nvidia revenue by segment in the most recent 10-Q?", "ground_truth": "Nvidia segment revenue table from the most recent 10-Q note on segment information.", "ticker": "NVDA", "filing_type": "10-Q", "difficulty": "table", "source": "custom"},
  {"question": "What was Apple's exact revenue breakdown by product category in fiscal 2025?", "ground_truth": "Apple net sales by product from the fiscal 2025 10-K consolidated statements.", "ticker": "AAPL", "filing_type": "10-K", "difficulty": "table", "source": "custom"},
  {"question": "What was the exact geographic revenue breakdown for Microsoft in fiscal 2025?", "ground_truth": "Microsoft revenue by geography table from fiscal 2025 10-K.", "ticker": "MSFT", "filing_type": "10-K", "difficulty": "table", "source": "custom"},
  {"question": "What were JPMorgan's exact capital ratios in the most recent 10-Q?", "ground_truth": "JPMorgan CET1 ratio and other capital ratios from the most recent 10-Q capital table.", "ticker": "JPM", "filing_type": "10-Q", "difficulty": "table", "source": "custom"},
  {"question": "What was Nvidia's exact gross profit breakdown by segment in the most recent 10-Q?", "ground_truth": "Nvidia gross profit by segment from the segment information note in the most recent 10-Q.", "ticker": "NVDA", "filing_type": "10-Q", "difficulty": "table", "source": "custom"},
  {"question": "What were Meta's exact operating expenses by category in the most recent 10-Q?", "ground_truth": "Meta costs and expenses table from the most recent 10-Q income statement.", "ticker": "META", "filing_type": "10-Q", "difficulty": "table", "source": "custom"},
  {"question": "What was Tesla's exact cash flow from operations in the most recent 10-Q?", "ground_truth": "Tesla net cash provided by operating activities from the most recent 10-Q cash flow statement.", "ticker": "TSLA", "filing_type": "10-Q", "difficulty": "table", "source": "custom"},
  {"question": "What were Google's exact advertising revenue figures by platform in the most recent 10-Q?", "ground_truth": "Alphabet Google advertising revenue breakdown by property from the most recent 10-Q.", "ticker": "GOOGL", "filing_type": "10-Q", "difficulty": "table", "source": "custom"},
  {"question": "What was Visa's exact payment volume breakdown by region in the most recent 10-Q?", "ground_truth": "Visa payments volume by geography from the most recent 10-Q operating metrics table.", "ticker": "V", "filing_type": "10-Q", "difficulty": "table", "source": "custom"},
  {"question": "What were AMD's exact segment revenues and operating income in the most recent 10-Q?", "ground_truth": "AMD segment information table from the most recent 10-Q note on segments.", "ticker": "AMD", "filing_type": "10-Q", "difficulty": "table", "source": "custom"}
]
```

**Note:** This file has 60 questions covering all four difficulty tiers. We need 150 total — the remaining 90 are added in the next step.

- [ ] **Step 2: Extend to 150 questions**

Append 90 more questions to reach 150 total. Run this to check current count:

```bash
python3 -c "import json; qs=json.load(open('evals/datasets/custom_150.json')); print(len(qs), 'questions'); print({d: sum(1 for q in qs if q['difficulty']==d) for d in ['easy','medium','hard','table']})"
```

Add more questions by editing the file to bring each tier to:
- easy: 50 questions total (tech, finance, healthcare, energy companies)
- medium: 50 questions total
- hard (multi-company): 30 questions total  
- table-specific: 20 questions total

The 60 questions above give you the pattern — follow the same `{question, ground_truth, ticker, filing_type, difficulty, source}` structure for each addition.

- [ ] **Step 3: Verify the final dataset**

```bash
python3 -c "
import json
qs = json.load(open('evals/datasets/custom_150.json'))
print(f'Total: {len(qs)}')
by_diff = {}
for q in qs:
    by_diff[q['difficulty']] = by_diff.get(q['difficulty'], 0) + 1
print('By difficulty:', by_diff)
assert len(qs) == 150, f'Need 150, got {len(qs)}'
print('OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add evals/datasets/custom_150.json
git commit -m "feat: add 150 custom eval questions across four difficulty tiers"
```

---

### Task 4: ragas_metrics.py

ragas needs a LangChain-wrapped Bedrock LLM + embeddings to judge answer quality. This module provides a single `score_sample()` function and a `score_dataset()` batch function. Unit tests mock the ragas `evaluate()` call.

**Files:**
- Create: `evals/metrics/ragas_metrics.py`
- Create: `tests/unit/test_ragas_metrics.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_ragas_metrics.py`:

```python
from unittest.mock import MagicMock, patch

from evals.metrics.ragas_metrics import build_ragas_config, score_dataset


def test_score_dataset_returns_expected_keys():
    mock_result = MagicMock()
    mock_result.to_pandas.return_value.__getitem__ = lambda self, k: MagicMock(mean=lambda: 0.9)

    with patch("evals.metrics.ragas_metrics.evaluate", return_value=mock_result):
        with patch("evals.metrics.ragas_metrics.ChatBedrock"):
            with patch("evals.metrics.ragas_metrics.BedrockEmbeddings"):
                config = build_ragas_config("us-east-1")
                samples = [
                    {
                        "question": "What was NVDA revenue?",
                        "answer": "Nvidia revenue was $26B [NVDA 10-Q 2026]",
                        "contexts": ["Nvidia reported revenue of $26 billion"],
                        "ground_truth": "$26 billion",
                    }
                ]
                result = score_dataset(samples, config)

    assert "faithfulness" in result
    assert "answer_relevancy" in result
    assert "context_precision" in result
    assert "context_recall" in result


def test_build_ragas_config_returns_llm_and_embeddings():
    with patch("evals.metrics.ragas_metrics.ChatBedrock") as mock_llm:
        with patch("evals.metrics.ragas_metrics.BedrockEmbeddings") as mock_emb:
            config = build_ragas_config("us-east-1")

    assert "llm" in config
    assert "embeddings" in config
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/unit/test_ragas_metrics.py -v
```

Expected: FAIL (`cannot import name 'build_ragas_config'`)

- [ ] **Step 3: Implement ragas_metrics.py**

Create `evals/metrics/ragas_metrics.py`:

```python
"""ragas evaluation metrics wired to Bedrock LLM + embeddings.

Provides score_dataset() -- call it with a list of
{question, answer, contexts, ground_truth} dicts and get back a dict of
{faithfulness, answer_relevancy, context_precision, context_recall} floats.
"""
from __future__ import annotations

from typing import Any

from langchain_aws import BedrockEmbeddings, ChatBedrock
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

# Cross-region inference profile IDs (required for on-demand Bedrock access)
HAIKU_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
TITAN_EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"


def build_ragas_config(region: str = "us-east-1") -> dict[str, Any]:
    """Build the LLM + embeddings config ragas needs to judge answers.

    Args:
        region: AWS region for Bedrock.

    Returns:
        Dict with 'llm' and 'embeddings' keys (LangchainLLMWrapper instances).
    """
    llm = LangchainLLMWrapper(ChatBedrock(model_id=HAIKU_MODEL_ID, region_name=region))
    embeddings = LangchainEmbeddingsWrapper(
        BedrockEmbeddings(model_id=TITAN_EMBED_MODEL_ID, region_name=region)
    )
    return {"llm": llm, "embeddings": embeddings}


def score_dataset(
    samples: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, float]:
    """Score a list of QA samples with all four ragas metrics.

    Args:
        samples: List of dicts each with keys:
            question (str), answer (str), contexts (list[str]), ground_truth (str)
        config: Output of build_ragas_config().

    Returns:
        Dict with keys: faithfulness, answer_relevancy, context_precision, context_recall
        Each value is a float 0.0-1.0 (mean across all samples).
    """
    ragas_samples = [
        SingleTurnSample(
            user_input=s["question"],
            response=s["answer"],
            retrieved_contexts=s["contexts"],
            reference=s["ground_truth"],
        )
        for s in samples
    ]
    dataset = EvaluationDataset(samples=ragas_samples)
    metrics = [faithfulness, answer_relevancy, context_precision, context_recall]
    result = evaluate(
        dataset,
        metrics=metrics,
        llm=config["llm"],
        embeddings=config["embeddings"],
    )
    df = result.to_pandas()
    return {
        "faithfulness": float(df["faithfulness"].mean()),
        "answer_relevancy": float(df["answer_relevancy"].mean()),
        "context_precision": float(df["context_precision"].mean()),
        "context_recall": float(df["context_recall"].mean()),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/unit/test_ragas_metrics.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add evals/metrics/ragas_metrics.py tests/unit/test_ragas_metrics.py
git commit -m "feat: ragas_metrics.py -- faithfulness + 3 ragas metrics via Bedrock"
```

---

### Task 5: numerical_accuracy.py

Custom metric: extract every number from the answer, normalize formats, check each appears in at least one source chunk. Returns `matched / total` as a float 0.0–1.0. No new dependencies — uses `re` from stdlib.

**Files:**
- Create: `evals/metrics/numerical_accuracy.py`
- Create: `tests/unit/test_numerical_accuracy.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_numerical_accuracy.py`:

```python
from evals.metrics.numerical_accuracy import extract_numbers, normalize_number, score_numerical_accuracy


def test_extract_numbers_finds_dollars_percentages_billions():
    text = "Revenue was $26.4B with a gross margin of 74.6% and operating income of $16,909 million."
    numbers = extract_numbers(text)
    assert "26.4" in numbers or "26.4b" in numbers.lower() or any("26" in n for n in numbers)
    assert any("74" in n for n in numbers)


def test_normalize_number_strips_currency_and_suffix():
    assert normalize_number("$26.4B") == 26400000000.0
    assert normalize_number("74.6%") == 74.6
    assert normalize_number("16,909") == 16909.0
    assert normalize_number("$1.2 billion") == 1200000000.0
    assert normalize_number("23.4 million") == 23400000.0


def test_score_perfect_match():
    answer = "Revenue was $26.4 billion."
    chunks = ["Nvidia reported revenue of $26.4 billion for the quarter."]
    score = score_numerical_accuracy(answer, chunks)
    assert score == 1.0


def test_score_zero_when_no_match():
    answer = "Revenue was $99.9 billion."
    chunks = ["Nvidia reported revenue of $26.4 billion for the quarter."]
    score = score_numerical_accuracy(answer, chunks)
    assert score == 0.0


def test_score_partial_match():
    answer = "Revenue was $26.4 billion and margin was 55%."
    chunks = ["Revenue of $26.4 billion was reported."]
    score = score_numerical_accuracy(answer, chunks)
    assert 0.0 < score < 1.0


def test_score_no_numbers_returns_one():
    answer = "The company reported strong growth."
    chunks = ["Strong growth was observed."]
    score = score_numerical_accuracy(answer, chunks)
    assert score == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/unit/test_numerical_accuracy.py -v
```

Expected: FAIL (`cannot import name 'extract_numbers'`)

- [ ] **Step 3: Implement numerical_accuracy.py**

Create `evals/metrics/numerical_accuracy.py`:

```python
"""Custom numerical accuracy metric: % of numbers in answer grounded in source chunks."""
from __future__ import annotations

import re

# Matches: $26.4B, $1.2 billion, 74.6%, 16,909, 23.4 million, 1,234.56
_NUMBER_RE = re.compile(
    r"\$?\d[\d,]*\.?\d*\s*(?:billion|million|thousand|B|M|K|T)?%?",
    re.IGNORECASE,
)

_SUFFIX_MULTIPLIERS = {
    "billion": 1e9, "b": 1e9,
    "million": 1e6, "m": 1e6,
    "thousand": 1e3, "k": 1e3,
    "trillion": 1e12, "t": 1e12,
}


def extract_numbers(text: str) -> list[str]:
    """Return all number-like strings found in text."""
    return _NUMBER_RE.findall(text)


def normalize_number(raw: str) -> float:
    """Convert a number string to a float, handling B/M/K suffixes and commas."""
    raw = raw.strip()
    is_percent = raw.endswith("%")
    clean = raw.lstrip("$").rstrip("%").strip()

    suffix = ""
    for s in _SUFFIX_MULTIPLIERS:
        if clean.lower().endswith(s):
            suffix = s
            clean = clean[: -len(s)].strip()
            break

    try:
        value = float(clean.replace(",", ""))
    except ValueError:
        return 0.0

    if suffix:
        value *= _SUFFIX_MULTIPLIERS[suffix.lower()]

    return value


def score_numerical_accuracy(answer: str, source_chunks: list[str]) -> float:
    """Return fraction of numbers in answer that appear (normalized) in source chunks.

    Args:
        answer: The generated answer text.
        source_chunks: List of source chunk texts used to generate the answer.

    Returns:
        Float 0.0-1.0. Returns 1.0 if answer has no numbers (nothing to verify).
    """
    numbers = extract_numbers(answer)
    if not numbers:
        return 1.0

    all_source_text = " ".join(source_chunks)
    source_numbers = extract_numbers(all_source_text)
    source_normalized = {normalize_number(n) for n in source_numbers}

    matched = sum(
        1 for n in numbers if normalize_number(n) in source_normalized
    )
    return matched / len(numbers)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/unit/test_numerical_accuracy.py -v
```

Expected: PASS (6/6)

- [ ] **Step 5: Commit**

```bash
git add evals/metrics/numerical_accuracy.py tests/unit/test_numerical_accuracy.py
git commit -m "feat: numerical_accuracy.py -- custom number grounding eval metric"
```

---

### Task 6: run_ci_eval.py (30-question CI subset runner)

Picks the first 10 easy + 10 medium + 5 hard + 5 table questions from the combined dataset, calls `build_search_filings_answer()` directly for each, scores with ragas + numerical_accuracy, and saves to `evals/results/ci_latest.json`.

**Files:**
- Create: `evals/run_ci_eval.py`
- Create: `evals/results/.gitkeep`
- Create: `tests/unit/test_run_ci_eval.py`
- Modify: `.gitignore` (ignore `evals/results/*.json` except `.gitkeep`)

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_run_ci_eval.py`:

```python
import json
import os
from unittest.mock import MagicMock, patch

from evals.run_ci_eval import load_ci_questions, run_ci_eval


def test_load_ci_questions_returns_thirty():
    qs = load_ci_questions()
    assert len(qs) == 30
    difficulties = {q["difficulty"] for q in qs}
    assert "easy" in difficulties
    assert "medium" in difficulties


@patch("evals.run_ci_eval.score_dataset")
@patch("evals.run_ci_eval.score_numerical_accuracy")
@patch("evals.run_ci_eval.build_search_filings_answer")
@patch("evals.run_ci_eval.build_ragas_config")
@patch("evals.run_ci_eval.get_pinecone_index")
@patch("evals.run_ci_eval.load_bm25_index")
@patch("evals.run_ci_eval.boto3")
def test_run_ci_eval_saves_results(
    mock_boto3, mock_bm25, mock_pinecone, mock_ragas_config,
    mock_search, mock_num_acc, mock_score_dataset, tmp_path
):
    mock_search.return_value = {
        "answer": "Revenue was $26B",
        "citations": [{"ticker": "NVDA"}],
        "contexts": ["Nvidia revenue was $26B"],
    }
    mock_num_acc.return_value = 1.0
    mock_score_dataset.return_value = {
        "faithfulness": 0.9,
        "answer_relevancy": 0.85,
        "context_precision": 0.8,
        "context_recall": 0.75,
    }

    out_path = str(tmp_path / "ci_latest.json")
    run_ci_eval(out_path=out_path, n_questions=2)

    assert os.path.exists(out_path)
    result = json.load(open(out_path))
    assert "faithfulness" in result
    assert "numerical_accuracy" in result
    assert "n_questions" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/unit/test_run_ci_eval.py -v
```

Expected: FAIL (`cannot import name 'load_ci_questions'`)

- [ ] **Step 3: Implement run_ci_eval.py**

Create `evals/run_ci_eval.py`:

```python
"""30-question CI eval runner. Runs on every PR via GitHub Actions.

Usage:
    python3 evals/run_ci_eval.py

Requires live AWS credentials and PINECONE_API_KEY env var.
Output: evals/results/ci_latest.json
"""
from __future__ import annotations

import json
import os
import time
from functools import partial
from typing import Any

import boto3

from evals.metrics.numerical_accuracy import score_numerical_accuracy
from evals.metrics.ragas_metrics import build_ragas_config, score_dataset
from pipeline.sync_pinecone import embed_text, get_pinecone_index, load_bm25_index
from server.mcp_tools.search_filings import build_search_filings_answer

PROCESSED_BUCKET = "finrag-processed-filings"
BM25_INDEX_KEY = "bm25/index.pkl"
CI_SUBSET_SIZE = 30
DEFAULT_OUT = "evals/results/ci_latest.json"


def load_ci_questions(n: int = CI_SUBSET_SIZE) -> list[dict[str, Any]]:
    """Load a balanced CI subset from the combined eval dataset."""
    datasets_dir = os.path.join(os.path.dirname(__file__), "datasets")
    questions: list[dict[str, Any]] = []

    for filename in ("financebench_150.json", "custom_150.json"):
        path = os.path.join(datasets_dir, filename)
        if os.path.exists(path):
            with open(path) as f:
                questions.extend(json.load(f))

    # Pick a balanced subset: 10 easy + 10 medium + 5 hard + 5 table
    by_difficulty: dict[str, list] = {}
    for q in questions:
        d = q.get("difficulty", "easy")
        by_difficulty.setdefault(d, []).append(q)

    subset: list[dict[str, Any]] = []
    targets = {"easy": 10, "medium": 10, "hard": 5, "table": 5}
    for diff, count in targets.items():
        subset.extend(by_difficulty.get(diff, [])[:count])

    return subset[:n]


def run_ci_eval(out_path: str = DEFAULT_OUT, n_questions: int = CI_SUBSET_SIZE) -> dict[str, Any]:
    """Run the CI eval and save results to out_path.

    Args:
        out_path: Where to write the JSON results file.
        n_questions: How many questions to run (default 30).

    Returns:
        The results dict that was written to disk.
    """
    s3_client = boto3.client("s3")
    bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-1")
    pinecone_index = get_pinecone_index(
        api_key=os.environ["PINECONE_API_KEY"], index_name="finrag-filings"
    )
    bm25_index, bm25_chunks = load_bm25_index(s3_client, PROCESSED_BUCKET, BM25_INDEX_KEY)
    embed_fn = partial(embed_text, bedrock_client)
    ragas_config = build_ragas_config(region="us-east-1")

    questions = load_ci_questions(n=n_questions)
    ragas_samples: list[dict[str, Any]] = []
    num_acc_scores: list[float] = []

    for i, q in enumerate(questions):
        print(f"[{i+1}/{len(questions)}] {q['question'][:70]}...")
        try:
            result = build_search_filings_answer(
                query=q["question"],
                bedrock_client=bedrock_client,
                pinecone_index=pinecone_index,
                bm25_index=bm25_index,
                bm25_chunks=bm25_chunks,
                embed_fn=embed_fn,
            )
            answer = result.get("answer", "")
            contexts = result.get("contexts", [])

            ragas_samples.append({
                "question": q["question"],
                "answer": answer,
                "contexts": contexts if contexts else ["No context retrieved"],
                "ground_truth": q.get("ground_truth", ""),
            })
            num_acc_scores.append(score_numerical_accuracy(answer, contexts))
        except Exception as e:
            print(f"  FAILED: {e}")
            continue

        time.sleep(0.5)  # avoid Bedrock throttling

    ragas_scores = score_dataset(ragas_samples, ragas_config) if ragas_samples else {}
    numerical_accuracy = sum(num_acc_scores) / len(num_acc_scores) if num_acc_scores else 0.0

    results = {
        **ragas_scores,
        "numerical_accuracy": numerical_accuracy,
        "n_questions": len(ragas_samples),
        "n_failed": len(questions) - len(ragas_samples),
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {out_path}")
    for k, v in results.items():
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    return results


if __name__ == "__main__":
    run_ci_eval()
```

- [ ] **Step 4: Add contexts to search_filings return value**

The eval runner expects `result["contexts"]` — check if `build_search_filings_answer` returns it:

```bash
grep -n "contexts" "/Users/jaipal/FinRAG MCP/server/mcp_tools/search_filings.py"
```

If `contexts` is not in the return dict, add it. Open `server/mcp_tools/search_filings.py` and find the return statement in `build_search_filings_answer`. Add `"contexts": [c["text"] for c in reranked_chunks]` to the returned dict.

- [ ] **Step 5: Create results directory**

```bash
mkdir -p evals/results
touch evals/results/.gitkeep
```

Add to `.gitignore`:
```
evals/results/*.json
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python3 -m pytest tests/unit/test_run_ci_eval.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add evals/run_ci_eval.py tests/unit/test_run_ci_eval.py evals/results/.gitkeep .gitignore
git commit -m "feat: run_ci_eval.py -- 30-question CI eval runner with ragas + numerical accuracy"
```

---

### Task 7: run_eval.py (full 300-question runner)

Same pattern as run_ci_eval.py but runs all 300 questions, saves to `evals/results/full_<timestamp>.json`, and also runs Baseline A (dense-only, no rewrite/rerank) and Baseline B (BM25-only) for comparison.

**Files:**
- Create: `evals/run_eval.py`
- Create: `tests/unit/test_run_eval.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_run_eval.py`:

```python
import json
import os
from unittest.mock import MagicMock, patch

from evals.run_eval import load_all_questions, run_baseline_a, run_baseline_b


def test_load_all_questions_returns_up_to_300():
    qs = load_all_questions()
    assert len(qs) <= 300
    assert len(qs) > 0


@patch("evals.run_eval.get_pinecone_index")
@patch("evals.run_eval.embed_text")
def test_run_baseline_a_calls_pinecone_directly(mock_embed, mock_pinecone):
    mock_pinecone.return_value.query.return_value = {"matches": [
        {"metadata": {"text": "Revenue was $26B"}, "score": 0.9}
    ]}
    mock_embed.return_value = [0.1] * 1024

    result = run_baseline_a(
        query="What was Nvidia revenue?",
        pinecone_index=mock_pinecone.return_value,
        embed_fn=lambda t: [0.1] * 1024,
    )
    assert "answer" in result
    assert "contexts" in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/unit/test_run_eval.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement run_eval.py**

Create `evals/run_eval.py`:

```python
"""Full 300-question eval runner with baseline comparison.

Usage:
    python3 evals/run_eval.py

Runs: (1) full pipeline, (2) Baseline A (dense-only), (3) Baseline B (BM25-only).
Saves all three results to evals/results/full_<timestamp>.json.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from functools import partial
from typing import Any

import boto3

from evals.metrics.numerical_accuracy import score_numerical_accuracy
from evals.metrics.ragas_metrics import build_ragas_config, score_dataset
from pipeline.sync_pinecone import embed_text, get_pinecone_index, load_bm25_index
from server.mcp_tools.search_filings import build_search_filings_answer

PROCESSED_BUCKET = "finrag-processed-filings"
BM25_INDEX_KEY = "bm25/index.pkl"


def load_all_questions() -> list[dict[str, Any]]:
    """Load all questions from both datasets, up to 300."""
    datasets_dir = os.path.join(os.path.dirname(__file__), "datasets")
    questions: list[dict[str, Any]] = []
    for filename in ("financebench_150.json", "custom_150.json"):
        path = os.path.join(datasets_dir, filename)
        if os.path.exists(path):
            with open(path) as f:
                questions.extend(json.load(f))
    return questions[:300]


def run_baseline_a(
    query: str,
    pinecone_index: Any,
    embed_fn: Any,
    top_k: int = 5,
) -> dict[str, Any]:
    """Baseline A: dense-only Pinecone query, no rewrite, no rerank, no generation model."""
    vector = embed_fn(query)
    response = pinecone_index.query(vector=vector, top_k=top_k, include_metadata=True)
    contexts = [m["metadata"].get("text", "") for m in response.get("matches", [])]
    answer = " ".join(contexts[:2])[:500] if contexts else "No results found."
    return {"answer": answer, "contexts": contexts}


def run_baseline_b(
    query: str,
    bm25_index: Any,
    bm25_chunks: list[dict[str, Any]],
    top_k: int = 5,
) -> dict[str, Any]:
    """Baseline B: BM25-only keyword search, no dense retrieval, no generation model."""
    from rank_bm25 import BM25Okapi
    tokenized = query.lower().split()
    scores = bm25_index.get_scores(tokenized)
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    contexts = [bm25_chunks[i].get("text", "") for i in top_indices if i < len(bm25_chunks)]
    answer = " ".join(contexts[:2])[:500] if contexts else "No results found."
    return {"answer": answer, "contexts": contexts}


def _score_run(
    questions: list[dict[str, Any]],
    run_fn: Any,
    ragas_config: dict[str, Any],
) -> dict[str, Any]:
    """Run run_fn on all questions and return aggregated scores."""
    ragas_samples = []
    num_acc_scores = []
    for i, q in enumerate(questions):
        print(f"  [{i+1}/{len(questions)}] {q['question'][:60]}...")
        try:
            result = run_fn(q["question"])
            answer = result.get("answer", "")
            contexts = result.get("contexts", [])
            ragas_samples.append({
                "question": q["question"],
                "answer": answer,
                "contexts": contexts or ["No context"],
                "ground_truth": q.get("ground_truth", ""),
            })
            num_acc_scores.append(score_numerical_accuracy(answer, contexts))
        except Exception as e:
            print(f"    FAILED: {e}")
        time.sleep(0.3)

    ragas_scores = score_dataset(ragas_samples, ragas_config) if ragas_samples else {}
    return {
        **ragas_scores,
        "numerical_accuracy": sum(num_acc_scores) / len(num_acc_scores) if num_acc_scores else 0.0,
        "n_questions": len(ragas_samples),
    }


def main() -> None:
    s3_client = boto3.client("s3")
    bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-1")
    pinecone_index = get_pinecone_index(
        api_key=os.environ["PINECONE_API_KEY"], index_name="finrag-filings"
    )
    bm25_index, bm25_chunks = load_bm25_index(s3_client, PROCESSED_BUCKET, BM25_INDEX_KEY)
    embed_fn = partial(embed_text, bedrock_client)
    ragas_config = build_ragas_config(region="us-east-1")

    questions = load_all_questions()
    print(f"Running eval on {len(questions)} questions...")

    print("\n--- Full Pipeline ---")
    full_fn = lambda q: build_search_filings_answer(  # noqa: E731
        query=q, bedrock_client=bedrock_client, pinecone_index=pinecone_index,
        bm25_index=bm25_index, bm25_chunks=bm25_chunks, embed_fn=embed_fn,
    )
    full_results = _score_run(questions, full_fn, ragas_config)

    print("\n--- Baseline A (dense-only) ---")
    baseline_a_fn = lambda q: run_baseline_a(q, pinecone_index, embed_fn)  # noqa: E731
    baseline_a_results = _score_run(questions, baseline_a_fn, ragas_config)

    print("\n--- Baseline B (BM25-only) ---")
    baseline_b_fn = lambda q: run_baseline_b(q, bm25_index, bm25_chunks)  # noqa: E731
    baseline_b_results = _score_run(questions, baseline_b_fn, ragas_config)

    out = {
        "full_pipeline": full_results,
        "baseline_a_dense_only": baseline_a_results,
        "baseline_b_bm25_only": baseline_b_results,
        "timestamp": datetime.utcnow().isoformat(),
    }

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = f"evals/results/full_{ts}.json"
    os.makedirs("evals/results", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\nResults saved to {out_path}")
    print("\n| Metric | Full Pipeline | Baseline A | Baseline B |")
    print("|---|---|---|---|")
    for metric in ("faithfulness", "answer_relevancy", "context_precision", "context_recall", "numerical_accuracy"):
        fp = full_results.get(metric, 0)
        ba = baseline_a_results.get(metric, 0)
        bb = baseline_b_results.get(metric, 0)
        print(f"| {metric} | {fp:.3f} | {ba:.3f} | {bb:.3f} |")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/unit/test_run_eval.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add evals/run_eval.py tests/unit/test_run_eval.py
git commit -m "feat: run_eval.py -- full 300Q runner with baseline A and B comparison"
```

---

### Task 8: GitHub Actions ci.yml

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Lint
        run: ruff check .

      - name: Unit tests (no live AWS)
        run: |
          pytest tests/unit/test_html_processor.py \
                 tests/unit/test_chunker.py \
                 tests/unit/test_sync_pinecone.py \
                 tests/unit/test_bootstrap_corpus.py \
                 tests/unit/test_query_rewriter.py \
                 tests/unit/test_hybrid_retriever.py \
                 tests/unit/test_reranker.py \
                 tests/unit/test_numerical_verifier.py \
                 tests/unit/test_answer_generator.py \
                 tests/unit/test_ragas_metrics.py \
                 tests/unit/test_numerical_accuracy.py \
                 tests/unit/test_run_ci_eval.py \
                 tests/unit/test_run_eval.py \
                 -v

  ci-eval:
    runs-on: ubuntu-latest
    needs: lint-and-test
    if: github.event_name == 'pull_request'
    env:
      AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
      AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
      AWS_DEFAULT_REGION: us-east-1
      PINECONE_API_KEY: ${{ secrets.PINECONE_API_KEY }}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run 30-question CI eval
        run: python3 evals/run_ci_eval.py

      - name: Check faithfulness threshold
        run: |
          python3 -c "
          import json
          r = json.load(open('evals/results/ci_latest.json'))
          assert r['faithfulness'] >= 0.85, f'faithfulness {r[\"faithfulness\"]:.3f} < 0.85'
          assert r['numerical_accuracy'] >= 0.90, f'numerical_accuracy {r[\"numerical_accuracy\"]:.3f} < 0.90'
          print('All thresholds passed:', r)
          "

      - name: Upload eval results
        uses: actions/upload-artifact@v4
        with:
          name: ci-eval-results
          path: evals/results/ci_latest.json
```

- [ ] **Step 2: Add GitHub secrets**

In your GitHub repo → Settings → Secrets and variables → Actions → New repository secret. Add:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `PINECONE_API_KEY`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "feat: GitHub Actions CI -- lint + unit tests + 30Q eval gate on every PR"
```

---

### Task 9: Week 3 eval sequence diagram

**Files:**
- Create: `diagrams/week3-eval-sequence.mmd`

- [ ] **Step 1: Create the diagram**

Create `diagrams/week3-eval-sequence.mmd`:

```
sequenceDiagram
    participant GH as GitHub Actions (PR trigger)
    participant CI as ci.yml runner
    participant ER as run_ci_eval.py
    participant SF as build_search_filings_answer()
    participant RM as ragas_metrics.py
    participant NA as numerical_accuracy.py
    participant BK as Bedrock (Haiku judge)
    participant PC as Pinecone (finrag-filings)
    participant DS as evals/datasets/*.json

    GH->>CI: PR opened / pushed
    CI->>CI: ruff check . (lint)
    CI->>CI: pytest tests/unit/ (32+ unit tests)
    CI->>ER: python3 evals/run_ci_eval.py

    ER->>DS: load_ci_questions() -- 30 balanced questions
    DS-->>ER: 10 easy + 10 medium + 5 hard + 5 table

    loop for each of 30 questions
        ER->>SF: build_search_filings_answer(question)
        SF->>PC: hybrid BM25 + dense retrieval
        PC-->>SF: top 5 reranked chunks
        SF-->>ER: {answer, citations, contexts}
        ER->>NA: score_numerical_accuracy(answer, contexts)
        NA-->>ER: float 0.0-1.0
    end

    ER->>RM: score_dataset(30 samples, ragas_config)
    RM->>BK: Haiku judges faithfulness per sample
    BK-->>RM: per-sample scores
    RM-->>ER: {faithfulness, answer_relevancy, context_precision, context_recall}

    ER->>ER: write evals/results/ci_latest.json
    CI->>CI: assert faithfulness >= 0.85
    CI->>CI: assert numerical_accuracy >= 0.90
    CI-->>GH: PASS / FAIL

    Note over GH,CI: Fails the PR if either threshold is missed
    Note over RM,BK: ragas uses Haiku as LLM judge -- cheap, ~$0.01 per 30Q run
```

- [ ] **Step 2: Commit**

```bash
git add diagrams/week3-eval-sequence.mmd
git commit -m "docs: Week 3 eval pipeline sequence diagram"
```

---

### Task 10: Run full test suite + lint, update CLAUDE.md

- [ ] **Step 1: Run all unit tests**

```bash
python3 -m pytest tests/unit/test_html_processor.py \
       tests/unit/test_chunker.py \
       tests/unit/test_sync_pinecone.py \
       tests/unit/test_bootstrap_corpus.py \
       tests/unit/test_query_rewriter.py \
       tests/unit/test_hybrid_retriever.py \
       tests/unit/test_reranker.py \
       tests/unit/test_numerical_verifier.py \
       tests/unit/test_answer_generator.py \
       tests/unit/test_ragas_metrics.py \
       tests/unit/test_numerical_accuracy.py \
       tests/unit/test_run_ci_eval.py \
       tests/unit/test_run_eval.py \
       -v
```

Expected: all pass (should be ~45 tests total)

- [ ] **Step 2: Lint**

```bash
ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 3: Update CLAUDE.md Phase 11**

Update the current state block to:
```
Current week: 3
Last completed: all Week 3 code tasks -- ragas_metrics, numerical_accuracy,
  run_ci_eval (30Q), run_eval (300Q + baseline comparison), ci.yml, datasets
Branch: week3-eval-harness
Next task: run bootstrap_corpus.py (waiting for Bedrock verification),
  then run_ci_eval.py live, then run_eval.py for baseline comparison table
```

- [ ] **Step 4: Final commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md Phase 11 -- Week 3 code complete"
```

---

## Self-Review

**Spec coverage:**
- FinanceBench 150 download: Task 2 ✅
- Custom 150 questions: Task 3 ✅ (note: ground truths need verification post-bootstrap)
- ragas_metrics.py: Task 4 ✅
- numerical_accuracy.py: Task 5 ✅
- run_ci_eval.py: Task 6 ✅
- run_eval.py + baselines: Task 7 ✅
- GitHub Actions ci.yml: Task 8 ✅
- Sequence diagram: Task 9 ✅

**Gaps / notes:**
- `contexts` field in `build_search_filings_answer` return: Task 6 Step 4 explicitly flags this check
- Custom 150 ground truths: marked as needing post-bootstrap verification (honest limitation — can't verify against live data until bootstrap runs)
- Baseline A/B run as part of run_eval.py (full run only, not CI) — this keeps CI fast

**Type consistency check:**
- `score_dataset()` takes `list[dict]` with keys `question, answer, contexts, ground_truth` — consistent across run_ci_eval and run_eval ✅
- `score_numerical_accuracy(answer, chunks)` signature consistent ✅
- `build_ragas_config()` returns `{"llm": ..., "embeddings": ...}` used consistently ✅

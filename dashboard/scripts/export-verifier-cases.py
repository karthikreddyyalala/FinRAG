"""Exports (answer, source_chunks, expected_output) triples from the real
production numerical_verifier so the TypeScript port can be proven against
actual behavior, not a re-read of the code."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from server.retrieval.numerical_verifier import verify_answer

CASES = [
    {
        "name": "exact match passes (comma-formatted number)",
        "answer": "3M's capital expenditure in FY2018 was $1,577.",
        "chunks": ["Purchases of property, plant and equipment (PP&E) ... $1,577 ... 2018"],
    },
    {
        "name": "substring trap: 1,234 must not match inside 1,234.56",
        "answer": "Revenue was $1,234 million.",
        "chunks": ["Total revenue for the period was $1,234.56 million."],
    },
    {
        "name": "percentage match",
        "answer": "Gross margin was 47.2%.",
        "chunks": ["Gross margin percentage: 47.2%"],
    },
    {
        "name": "parenthesized negative in source matches unsigned answer",
        "answer": "Cash used in operations was $1,577.",
        "chunks": ["Net cash used: $(1,577) thousand"],
    },
    {
        "name": "number not in any chunk gets replaced",
        "answer": "Revenue was $9,999 million.",
        "chunks": ["Total revenue: $1,234 million"],
    },
    {
        "name": "multiple numbers, one grounded one not",
        "answer": "Revenue was $1,234 and margin was 99.9%.",
        "chunks": ["Total revenue: $1,234 million. Gross margin: 47.2%"],
    },
    {
        "name": "bare percentage with decimal, no dollar sign",
        "answer": "Growth rate was 3.5%, up from 2%.",
        "chunks": ["The company reported 3.5% growth this quarter, compared to 2% last year."],
    },
    {
        "name": "large number without dollar sign or percent (comma-grouped)",
        "answer": "Total assets were 1,234,567.",
        "chunks": ["Total assets: 1,234,567"],
    },
    {
        "name": "number with billion suffix, dollar sign required for that branch",
        "answer": "Revenue was $23.4 billion.",
        "chunks": ["Revenue: $23.4 billion in the period"],
    },
    {
        "name": "no numbers in answer at all",
        "answer": "The company did not disclose a specific figure.",
        "chunks": ["Some unrelated source text with $500 in it."],
    },
]

results = []
for case in CASES:
    output = verify_answer(case["answer"], case["chunks"])
    results.append({**case, "expected": output})

out_path = Path(__file__).resolve().parent.parent / "lib" / "verifier-cases.json"
out_path.write_text(json.dumps(results, indent=2) + "\n")
print(f"Exported {len(results)} cases to {out_path}")
for r in results:
    print(f"  - {r['name']}: {r['expected']!r}")

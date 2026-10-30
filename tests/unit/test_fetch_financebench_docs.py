from evals.fetch_financebench_docs import parse_rows


def test_parse_rows_keeps_question_doc_and_evidence():
    raw = (
        '{"question": "Q one", "doc_name": "3M_2018_10K", "company": "3M", '
        '"evidence": [{"evidence_text": "Purchases of PP&E (1,577)"}], "answer": "$1577.00"}\n'
    )
    rows = parse_rows(raw)
    assert rows == [{
        "question": "Q one", "doc_name": "3M_2018_10K", "company": "3M",
        "evidence": ["Purchases of PP&E (1,577)"], "ground_truth": "$1577.00",
    }]

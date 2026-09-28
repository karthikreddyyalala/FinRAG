"""Unit test for run_eval.py's placeholder-filtering logic.

The rest of run_eval.py calls live Bedrock/Pinecone/DynamoDB and is
exercised by actually running it (see claude.md), not by a unit test.
"""
from evals.run_eval import verified_custom_items


def test_verified_custom_items_drops_unverified_placeholders():
    items = [
        {"question": "a", "ground_truth": "VERIFY_AFTER_BOOTSTRAP"},
        {"question": "b", "ground_truth": "$94036.00"},
        {"question": "c", "ground_truth": "60.5%"},
    ]
    result = verified_custom_items(items)
    assert [i["question"] for i in result] == ["b", "c"]


def test_verified_custom_items_empty_input():
    assert verified_custom_items([]) == []

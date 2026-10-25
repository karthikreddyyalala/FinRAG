from server.retrieval.ratio_plan import add_per_item_winners, line_items_for


def test_ratio_questions_expand_to_the_statement_lines_they_need():
    q = "What is Coca Cola's FY2021 COGS % margin? Calculate it from the income statement."
    assert line_items_for(q) == ["net sales", "cost of sales"]
    assert line_items_for("What is the FY2019 inventory turnover ratio for Kraft Heinz?") == [
        "cost of sales", "inventories",
    ]
    assert line_items_for("Does AMD have positive working capital in FY22?") == [
        "total current assets", "total current liabilities",
    ]


def test_a_plain_lookup_has_no_line_items():
    assert line_items_for("What was 3M's capital expenditure in fiscal year 2018?") == []


def test_overlapping_ratios_do_not_repeat_a_line():
    q = "Compare gross margin and operating margin for Nike in FY2020."
    assert line_items_for(q) == ["net sales", "cost of sales", "operating income"]


def test_short_terms_match_whole_words_only():
    assert line_items_for("What does the DPO look like?") == ["accounts payable", "cost of sales"]
    assert line_items_for("A sandpot of roast data") == []


def test_each_missing_line_gets_its_best_chunk_added_up_to_the_cap():
    base = [{"chunk_id": "a"}, {"chunk_id": "b"}]
    winners = [[{"chunk_id": "b"}, {"chunk_id": "c"}], [{"chunk_id": "d"}], [{"chunk_id": "e"}]]
    out = add_per_item_winners(base, winners, cap=4)
    assert [c["chunk_id"] for c in out] == ["a", "b", "c", "d"]

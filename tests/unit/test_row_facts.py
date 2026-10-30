from pipeline.row_facts import table_row_facts

TABLE = (
    "0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10\n"
    "Years ended December 31 |  |  |  |  |  |  |  |  |  | \n"
    "(Millions) |  | 2018 | 2018 |  | 2017 | 2017 |  | 2016 | 2016 | \n"
    "Purchases of property, plant and equipment (PP&E) |  | $ | (1,577) |  | $ | (1,373) |"
    " |  | $ | (1,420) | \n"
    "Net cash provided by operating activities |  | $ | 6439 |  | $ | 6240 |  | $ | 6662 | \n"
)
META = {"ticker": "MMM", "filing_type": "10-K", "period": "2019-02-07"}


def test_one_fact_per_numeric_row_with_years():
    facts = table_row_facts(TABLE, META)
    texts = [f["text"] for f in facts]
    assert any(
        "Purchases of property, plant and equipment (PP&E)" in t
        and "2018: (1,577)" in t
        and "2017: (1,373)" in t
        for t in texts
    )
    assert len(facts) == 2
    assert all(f["chunk_type"] == "fact" and f["ticker"] == "MMM" for f in facts)


def test_table_without_year_header_yields_nothing():
    assert table_row_facts("A | B\nrevenue | 5", META) == []


def test_fact_ids_are_stable_so_reingest_overwrites():
    a = table_row_facts(TABLE, META)
    b = table_row_facts(TABLE, META)
    assert [f["chunk_id"] for f in a] == [f["chunk_id"] for f in b]
    # a recognisable prefix lets the whole batch be listed and deleted by id
    assert all(f["chunk_id"].startswith("fact_") for f in a)


def test_row_with_more_values_than_years_is_skipped_not_misaligned():
    table = (
        "(Millions) |  | 2025 | 2025 |  | 2024 | 2024\n"
        "Interest income |  | 46 |  | 46 |  | 40 |  | 41\n"
    )
    assert table_row_facts(table, META) == []


def test_row_repeating_one_value_for_every_year_is_a_parse_artifact_and_skipped():
    table = (
        "(Millions) |  | 2025 |  | 2024 |  | 2023\n"
        "Electronics |  | 2911 |  | 2911.0 |  | 2911.0\n"
        "Real row |  | 10 |  | 20 |  | 30\n"
    )
    facts = table_row_facts(table, META)
    assert [f["text"].split(": ")[1] for f in facts] == ["Real row"]

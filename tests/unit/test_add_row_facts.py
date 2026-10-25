from scripts.add_row_facts import new_facts

TABLE = (
    "(Millions) |  | 2018 | 2018 |  | 2017 | 2017\n"
    "Purchases of PP&E |  | $ | (1,577) |  | $ | (1,373)\n"
)


def chunk(kind, form, text=TABLE):
    return {"chunk_id": "x", "chunk_type": kind, "filing_type": form, "ticker": "MMM",
            "period": "2019-02-07", "text": text}


def test_only_annual_report_tables_become_facts():
    cached = [chunk("table", "10-K"), chunk("table", "10-Q"), chunk("child", "10-K")]
    facts = new_facts(cached)
    assert len(facts) == 1 and facts[0]["filing_type"] == "10-K"


def test_facts_already_in_the_cache_are_not_made_again():
    cached = [chunk("table", "10-K")]
    first = new_facts(cached)
    assert new_facts(cached + first) == []

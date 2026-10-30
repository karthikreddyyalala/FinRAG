from server.retrieval.numerical_verifier import check_figures

SOURCE = "Purchases of property, plant and equipment (PP&E) $ | (1,577) | (1,373)"


def test_figure_in_the_source_is_grounded_even_across_table_formatting():
    grounded, not_found = check_figures("3M spent $1,577 million on capex.", [SOURCE])
    assert grounded == ["$1,577 million"]
    assert not_found == []


def test_figure_missing_from_the_source_is_reported():
    grounded, not_found = check_figures("Capex was $1,234 million, up from $1,373.", [SOURCE])
    assert not_found == ["$1,234 million"]
    assert grounded == ["$1,373"]


def test_a_rounded_figure_does_not_match_a_more_precise_one():
    """$1,234 is not $1,234.56: substring matching let this through once."""
    _, not_found = check_figures("Revenue was $1,234.", ["Revenue $1,234.56"])
    assert not_found == ["$1,234"]


def test_answer_without_figures_has_nothing_to_check():
    assert check_figures("The filing does not say.", [SOURCE]) == ([], [])

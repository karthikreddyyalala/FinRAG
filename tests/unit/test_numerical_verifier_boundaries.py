"""TDD: numerical grounding must not be fooled by numeric prefixes.

These are silent failures of the project's flagship guarantee -- one lets a
hallucinated figure through, the others corrupt otherwise-valid text.
"""
from server.retrieval.numerical_verifier import extract_numbers, verify_answer


def test_prefix_of_a_source_number_is_not_treated_as_grounded():
    """A hallucinated $1,234 must NOT pass just because a source has $1,234.56."""
    answer = "Total revenue reached $1,234."
    sources = ["The filing reports $1,234.56 million in revenue."]

    result = verify_answer(answer, sources)

    assert "exact figure unavailable" in result, (
        f"hallucinated prefix passed as grounded: {result!r}"
    )


def test_grounded_number_is_not_mangled_by_an_ungrounded_prefix():
    """Replacing an ungrounded $9,999 must not corrupt a grounded $9,999.99."""
    answer = "Costs were $9,999 and revenue was $9,999.99."
    sources = ["Revenue was $9,999.99 for the year."]

    result = verify_answer(answer, sources)

    assert "$9,999.99" in result, f"grounded number was mangled: {result!r}"
    assert "exact figure unavailable" in result, f"ungrounded number kept: {result!r}"


def test_extraction_does_not_swallow_sentence_punctuation():
    """The comma after $1,234 is sentence punctuation, not part of the number."""
    assert extract_numbers("Revenue was $1,234, and costs $500.") == ["$1,234", "$500"]


def test_replacement_preserves_surrounding_punctuation():
    """Replacing an ungrounded number must not eat the following comma/space."""
    answer = "Revenue was $1,234, up sharply."
    sources = ["No matching figures here."]

    result = verify_answer(answer, sources)

    assert result == "Revenue was [exact figure unavailable in retrieved context], up sharply.", (
        f"punctuation lost: {result!r}"
    )


def test_grounded_numbers_pass_through_unchanged():
    answer = "Revenue was $26.4 billion, up 12.5%."
    sources = ["Revenue was $26.4 billion this year, an increase of 12.5% over last."]

    assert verify_answer(answer, sources) == answer

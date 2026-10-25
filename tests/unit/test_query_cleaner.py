from server.retrieval.query_cleaner import clean_question


def test_persona_and_format_filler_is_removed_but_the_question_stays():
    q = (
        "Assume that you are a public equities analyst. Answer the following question by "
        "primarily using information that is shown in the balance sheet: what is the year "
        "end FY2018 net PPNE for 3M? Answer in USD billions."
    )
    assert clean_question(q) == "what is the year end FY2018 net PPNE for 3M?"


def test_rounding_and_not_relevant_boilerplate_is_removed():
    q = (
        "What drove operating margin change as of FY2022 for 3M? If operating margin is not "
        "a useful metric for a company like this, then please state that and explain why."
    )
    assert clean_question(q) == "What drove operating margin change as of FY2022 for 3M?"
    assert clean_question("What was Apple revenue? Round your answer to two decimal places.") == (
        "What was Apple revenue?"
    )


def test_a_short_plain_question_is_unchanged():
    q = "What was 3M's capital expenditure in fiscal year 2018?"
    assert clean_question(q) == q


def test_if_everything_looks_like_filler_the_original_is_kept():
    q = "Answer in USD millions."
    assert clean_question(q) == q

from server.retrieval.numerical_verifier import extract_numbers, verify_answer


def test_extract_numbers_finds_dollar_amounts_and_percentages():
    text = "Revenue grew to $9.06 billion, a 78% increase, with $23,400 million in total."

    numbers = extract_numbers(text)

    assert "$9.06 billion" in numbers
    assert "78%" in numbers
    assert "$23,400 million" in numbers


def test_verify_answer_keeps_numbers_found_in_source_chunks():
    answer = "Nvidia's data center revenue was $9.06 billion, a 78% increase."
    source_chunks = [
        "Data center revenue reached $9.06 billion this quarter, "
        "up 78% year over year."
    ]

    verified = verify_answer(answer, source_chunks)

    assert "$9.06 billion" in verified
    assert "78%" in verified
    assert "exact figure unavailable" not in verified


def test_verify_answer_flags_numbers_not_found_in_source_chunks():
    answer = "Nvidia's revenue was $50 billion this quarter."
    source_chunks = ["Nvidia's revenue was $9.06 billion this quarter."]

    verified = verify_answer(answer, source_chunks)

    assert "$50 billion" not in verified
    assert "exact figure unavailable" in verified


def test_verify_answer_replaces_all_occurrences_of_ungrounded_number():
    answer = "Revenue was $50 billion in Q1 and $50 billion in Q2."
    source_chunks = ["Revenue was $9.06 billion"]

    verified = verify_answer(answer, source_chunks)

    assert verified.count("[exact figure unavailable") == 2

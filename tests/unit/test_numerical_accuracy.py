from evals.metrics.numerical_accuracy import numerical_accuracy, _normalise, _extract_numbers


def test_normalise_billion():
    assert _normalise("$26.4B") == pytest_approx(26_400_000_000.0)


def test_normalise_million():
    assert _normalise("23,400 million") == pytest_approx(23_400_000_000.0)


def test_normalise_percent():
    assert _normalise("47.2%") == pytest_approx(47.2)


def test_extract_finds_dollar_and_percent():
    nums = _extract_numbers("Revenue was $23.4B, up 18.5%.")
    assert len(nums) == 2


def test_numerical_accuracy_perfect():
    answers = ["Revenue was $23.4B"]
    contexts = [["Revenue was $23.4B in the period."]]
    assert numerical_accuracy(answers, contexts) == 1.0


def test_numerical_accuracy_miss():
    answers = ["Revenue was $99.9B"]
    contexts = [["Revenue was $23.4B in the period."]]
    assert numerical_accuracy(answers, contexts) == 0.0


def test_numerical_accuracy_empty_numbers():
    answers = ["Revenue grew significantly."]
    contexts = [["Revenue grew significantly."]]
    assert numerical_accuracy(answers, contexts) == 1.0


def test_numerical_accuracy_format_normalisation():
    answers = ["Revenue was $26.4 billion"]
    contexts = [["Revenue was 26,400 million."]]
    assert numerical_accuracy(answers, contexts) == 1.0


import pytest
from pytest import approx as pytest_approx

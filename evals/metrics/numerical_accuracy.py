"""Custom metric: % of numbers in an answer that appear in source chunks."""
import re

_NUMBER_RE = re.compile(
    r"\$?\d[\d,]*\.?\d*\s*(?:[BMKTbmkt](?:illion|rillion)?)?\b|"
    r"\d+\.?\d*\s*%"
)

_SUFFIX = {"b": 1e9, "billion": 1e9, "m": 1e6, "million": 1e6,
           "k": 1e3, "thousand": 1e3, "t": 1e12, "trillion": 1e12}


def _normalise(raw: str) -> float:
    """Convert '$26.4B', '26,400 million', '26.4%' → float."""
    s = raw.lower().replace(",", "").replace("$", "").strip()
    for suffix, mult in _SUFFIX.items():
        if s.endswith(suffix):
            return float(s[: -len(suffix)].strip()) * mult
    return float(s.rstrip("%"))


def _extract_numbers(text: str) -> list[float]:
    nums = []
    for m in _NUMBER_RE.finditer(text):
        try:
            nums.append(_normalise(m.group()))
        except ValueError:
            pass
    return nums


def _found_in_contexts(value: float, contexts: list[str], tol: float = 0.01) -> bool:
    for ctx in contexts:
        for n in _extract_numbers(ctx):
            if n != 0 and abs(value - n) / max(abs(n), 1e-9) <= tol:
                return True
            if n == 0 and value == 0:
                return True
    return False


def numerical_accuracy(
    answers: list[str],
    contexts: list[list[str]],
) -> float:
    """Fraction of numbers in each answer that appear in source chunks, averaged.

    This is PRECISION ONLY. It has no recall term: it never checks whether the
    question was answered, or answered correctly. An answer containing no
    numbers scores a perfect 1.0 (see below), so the degenerate strategy that
    maximises this metric is to refuse every question.

    That is not hypothetical. It silently inverted this project's own baseline
    comparison: BM25-only retrieval refused 133/150 questions, scored the
    highest numerical_accuracy of the three configurations, and was written up
    as "keyword search beat the full pipeline" until the refusal rates were
    checked. See evals/analyze_baseline_gap.py.

    Use it to ask "is this particular answer grounded". Do NOT use it alone to
    rank retrieval strategies against each other -- pair it with a correctness
    measure that penalises not answering.
    """
    if not answers:
        return 0.0
    sample_scores: list[float] = []
    for answer, ctxs in zip(answers, contexts):
        nums = _extract_numbers(answer)
        if not nums:
            # Vacuously grounded: an answer claiming no figures cannot state an
            # ungrounded one. Correct for a precision metric, and precisely why
            # this score rewards refusal -- see the docstring before ranking
            # anything with it.
            sample_scores.append(1.0)
            continue
        hits = sum(1 for n in nums if _found_in_contexts(n, ctxs))
        sample_scores.append(hits / len(nums))
    return sum(sample_scores) / len(sample_scores)

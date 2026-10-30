"""Post-generation numerical grounding: every number must appear in a source chunk.

CLAUDE.md Phase 9 constraint #1: every number in the answer MUST appear
verbatim (in some format) in a retrieved chunk. This is a Week 2 baseline
implementation -- exact-substring matching after normalizing common dollar
formats, not full unit-conversion equivalence ("23,400 million" == "23.4
billion" is a documented Week 3+ gap, not attempted here).
"""
from __future__ import annotations

import re

NUMBER_PATTERN = re.compile(
    # Dollar amounts. The digit run may not end on a comma -- `[\d,]+` would
    # otherwise swallow the sentence comma in "$1,234, and costs ...".
    r"\$\d[\d,]*(?:\.\d+)?(?:\s?(?:billion|million|thousand|B|M|K))?\b"
    r"|\d+(?:\.\d+)?%"  # percentages
    r"|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"  # large comma-separated numbers
)


def extract_numbers(text: str) -> list[str]:
    """Extract dollar amounts, percentages, and large numbers from text.

    Args:
        text: Text to scan (typically a generated answer).

    Returns:
        List of matched number substrings, in order of appearance.
    """
    return NUMBER_PATTERN.findall(text)


_NUMERIC_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numeric_value(token: str) -> float | None:
    """Parse a formatted figure to its magnitude, or None if unparseable.

    Magnitude, not signed value: financial tables wrap negatives in
    parentheses -- "(1,577)" is 1,577 of cash outflow -- and an answer
    correctly reporting the amount spent writes "$1,577".
    """
    digits = _NUMERIC_TOKEN.search(token)
    if not digits:
        return None
    try:
        return float(digits.group().replace(",", ""))
    except ValueError:
        return None


def _source_values(sources: str) -> set[float]:
    """Every numeric magnitude appearing anywhere in the source chunks."""
    values: set[float] = set()
    for match in _NUMERIC_TOKEN.finditer(sources):
        value = _numeric_value(match.group())
        if value is not None:
            values.add(value)
    return values


def _is_grounded(number: str, source_values: set[float]) -> bool:
    """True if `number` matches a figure in the sources by value.

    Compared numerically rather than as text. Table cells split the currency
    symbol from the value ("$ | (1,577)") and wrap negatives in parentheses,
    so a correct answer saying "$1,577 million" shares no literal substring
    with its own source. Comparing values also preserves the property that
    matching by substring lost: 1234 != 1234.56, so a fabricated "$1,234" is
    still caught when the source only holds "$1,234.56".
    """
    value = _numeric_value(number)
    return value is not None and value in source_values


def verify_answer(answer: str, source_chunks: list[str]) -> str:
    """Remove any number in the answer that doesn't appear in a source chunk.

    Args:
        answer: The generated answer text.
        source_chunks: Raw text of the chunks the answer was generated from.

    Returns:
        The answer with each ungrounded number replaced inline by
        "[exact figure unavailable in retrieved context]". No summary
        note is appended -- the qualifier appears at each occurrence.
    """
    source_values = _source_values(" ".join(source_chunks))

    # Rewrite right-to-left by match span so earlier offsets stay valid, and
    # so a replacement never touches text outside the matched number. A
    # str.replace() of "$9,999" would also corrupt a grounded "$9,999.99".
    out = answer
    for match in reversed(list(NUMBER_PATTERN.finditer(answer))):
        if _is_grounded(match.group(), source_values):
            continue
        out = (
            out[: match.start()]
            + "[exact figure unavailable in retrieved context]"
            + out[match.end() :]
        )
    return out


def check_figures(answer: str, source_chunks: list[str]) -> tuple[list[str], list[str]]:
    """Split the answer's figures into (grounded, not_found) against the sources.

    Same matching as verify_answer (parsed magnitude, so "(1,577)" grounds
    "$1,577 million" but "$1,234.56" does not ground "$1,234"); reports
    instead of rewriting, for clients that write their own answers.
    """
    source_values = _source_values(" ".join(source_chunks))
    grounded: list[str] = []
    not_found: list[str] = []
    for match in NUMBER_PATTERN.finditer(answer):
        target = grounded if _is_grounded(match.group(), source_values) else not_found
        target.append(match.group())
    return grounded, not_found


_SCALE = {"billion": 1e9, "b": 1e9, "million": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}
_FIGURE = re.compile(r"(\d[\d,]*)(?:\.(\d+))?\s?(billion|million|thousand|B|M|K)?\b")


def _matches_value(figure: str, value: float) -> bool:
    """Does `figure` state `value`, rounded to the precision it is written at?

    "$33.7 billion" states 33,723,297,000 (within 0.05 billion) but "$33,700
    million" does not (that claims precision to the million). A figure without
    a scale word is also read as thousands, millions or billions, the units
    filings print in.
    """
    m = _FIGURE.search(figure)
    if not m:
        return False
    whole, frac, unit = m.groups()
    number = float(whole.replace(",", "") + (f".{frac}" if frac else ""))
    half_step = 0.5 * 10 ** -(len(frac) if frac else 0)
    scales = [_SCALE[unit.lower()]] if unit else [1, 1e3, 1e6, 1e9]
    return any(abs(number * s - abs(value)) <= half_step * s + 1e-9 for s in scales)


def check_figures_against_values(
    answer: str, values: list[float]
) -> tuple[list[str], list[str]]:
    """(grounded, not_found) for the answer's figures against exact reported values.

    For XBRL facts, which are stored in full units: 33,723,297,000 grounds
    "$33,723.3 million" and "$33.7 billion" but not "$34.7 billion". Percentages
    are never grounded here; a ratio is computed, not reported.
    """
    grounded: list[str] = []
    not_found: list[str] = []
    for match in NUMBER_PATTERN.finditer(answer):
        figure = match.group()
        hit = not figure.endswith("%") and any(_matches_value(figure, v) for v in values)
        (grounded if hit else not_found).append(figure)
    return grounded, not_found

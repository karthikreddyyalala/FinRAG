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
    r"\$[\d,]+(?:\.\d+)?\s?(?:billion|million|thousand|B|M|K)?"  # dollar amounts
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
    combined_sources = " ".join(source_chunks)
    numbers = extract_numbers(answer)
    ungrounded = [n for n in numbers if n not in combined_sources]

    verified = answer
    for number in ungrounded:
        verified = verified.replace(
            number, "[exact figure unavailable in retrieved context]"
        )

    return verified

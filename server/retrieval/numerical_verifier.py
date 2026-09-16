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


def _is_grounded(number: str, sources: str) -> bool:
    """True if `number` appears in `sources` as a whole number, not a prefix.

    Plain substring matching is unsafe here: a hallucinated "$1,234" is a
    substring of a legitimate "$1,234.56", so the check would pass and the
    fabricated figure would reach the user. Requiring that the match not be
    followed by a digit (or a decimal point starting more digits) closes that.
    """
    for match in re.finditer(re.escape(number), sources):
        tail = sources[match.end() : match.end() + 2]
        if tail[:1].isdigit():
            continue
        if tail[:1] == "." and tail[1:2].isdigit():
            continue
        return True
    return False


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

    # Rewrite right-to-left by match span so earlier offsets stay valid, and
    # so a replacement never touches text outside the matched number. A
    # str.replace() of "$9,999" would also corrupt a grounded "$9,999.99".
    out = answer
    for match in reversed(list(NUMBER_PATTERN.finditer(answer))):
        if _is_grounded(match.group(), combined_sources):
            continue
        out = (
            out[: match.start()]
            + "[exact figure unavailable in retrieved context]"
            + out[match.end() :]
        )
    return out

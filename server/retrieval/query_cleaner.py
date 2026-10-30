"""Strip prompt boilerplate from a question before searching with it.

Benchmark-style questions carry persona and formatting instructions ("Assume
that you are a public equities analyst", "Round your answer to two decimal
places"). They add words that match nothing in a filing and drown the few terms
that do. The cleaned text is used for retrieval only; generation still sees the
full question, because those instructions decide how the answer is written.
"""
from __future__ import annotations

import re

_SENTENCE_BREAK = re.compile(r"(?<=[.?!])\s+")

# A sentence that opens with one of these is an instruction, not a question.
_LEADING_INSTRUCTION = re.compile(
    r"^(?:assume that you are|answer the following question|respond to the question|"
    r"round your answer|answer in |give a response|calculate what was asked|"
    r"as if you are|please (?:state|round|answer))",
    re.IGNORECASE,
)
# "If X is not a useful metric ..., then please state that" tails.
_CONDITIONAL_FILLER = re.compile(
    r"^if .{0,80}\b(?:not|n't)\b .{0,40}\b(?:useful|relevant|applicable|meaningful)\b",
    re.IGNORECASE,
)


def clean_question(question: str) -> str:
    """Return the question with instruction sentences removed.

    An instruction that wraps the real question after a colon ("...shown in the
    balance sheet: what is X?") keeps the part after the colon. If nothing is
    left, the original question is returned unchanged.
    """
    kept: list[str] = []
    for sentence in _SENTENCE_BREAK.split(question.strip()):
        if _LEADING_INSTRUCTION.match(sentence):
            _, colon, rest = sentence.partition(":")
            if colon and rest.strip():
                kept.append(rest.strip())
            continue
        if _CONDITIONAL_FILLER.match(sentence):
            continue
        kept.append(sentence.strip())
    cleaned = " ".join(s for s in kept if s)
    return cleaned or question

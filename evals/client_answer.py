"""Plays the MCP client in evals: writes an answer from the server's passages.

In production the client's own model (Claude, Cursor, ...) does this. Evals
need one fixed, named model so scores are comparable across runs, and every
answer row records which model wrote it. Earlier results did not, and from
September to October 2026 they were silently written by a fallback model
rather than the one the site named.
"""
from __future__ import annotations

import os
import time
from typing import Any

import openai
from openai import OpenAI

DEFAULT_MODEL = "gpt-4o-mini"

# Grounding is the hard rule; the equivalences and the sign rule exist because
# without them the model refused figures it had found (FinanceBench Q1: it
# retrieved "Purchases of property, plant and equipment (PP&E) $(1,577)" and
# still said it could not determine capital expenditure).
SYSTEM_PROMPT = """Answer the question using only the provided context.

Grounding rules:
- Never state a number that does not appear verbatim in the context.
- If the context genuinely lacks the figure, say so. Do not guess.
- Cite every claim inline, e.g. [MMM 10-K 2019-02-07 p.40]

Reading financial statements:
- Filings label figures with their GAAP line item, not the analyst's term for
  them. Treat these as the same figure and answer directly:
    capital expenditures  = "Purchases of property, plant and equipment (PP&E)"
    revenue / top line    = "Net sales" / "Total revenues"
    COGS                  = "Cost of sales"
    operating cash flow   = "Net cash provided by operating activities"
- Parentheses around a number denote a negative or a cash outflow. For a
  question asking "how much was spent", report the magnitude: $(1,577) in a
  cash flow statement means $1,577 million of spending.
- Report the figure in the units the question asks for, converting between
  millions and billions where the context states its own units."""

USER_MESSAGE_TEMPLATE = """Context:
{context}

Question: {question}"""


def eval_model() -> str:
    """The model that writes eval answers: FINRAG_EVAL_MODEL, else gpt-4o-mini."""
    return os.environ.get("FINRAG_EVAL_MODEL", DEFAULT_MODEL)


def write_answer(
    question: str, passages: list[dict[str, Any]], model: str | None = None, client: Any = None
) -> str:
    """Answer from the passages (to_passage() shape), at temperature 0.

    Retries rate limits and connection errors (a transient blip once killed a
    150-question run at its last question), but not an empty balance:
    waiting cannot fix insufficient_quota.
    """
    context = "\n\n".join(f"{p['text']}\nCitation: {p['citation']}" for p in passages)
    client = client or OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_MESSAGE_TEMPLATE.format(context=context,
                                                                 question=question)},
    ]
    for attempt in range(8):
        try:
            response = client.chat.completions.create(
                model=model or eval_model(), temperature=0, max_tokens=1024, messages=messages,
            )
            return response.choices[0].message.content
        except Exception as e:
            text = str(e)
            if "insufficient_quota" in text:
                raise
            retriable = (
                isinstance(e, openai.APIConnectionError | openai.APITimeoutError)
                or "429" in text or "rate_limit" in text.lower()
            )
            if not retriable:
                raise
            wait = 15 * (attempt + 1)
            print(f"    [{type(e).__name__}] waiting {wait}s ...", flush=True)
            time.sleep(wait)
    raise RuntimeError("OpenAI: exhausted retries")

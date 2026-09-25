"""Per-query cost/latency logging to DynamoDB (Phase C, CLAUDE.md).

Token counts are estimated from text length (~4 chars/token), not read from
each API's exact usage field -- getting exact usage would mean threading a
new return value through rewrite_query() and generate_answer(), and every
existing call site (all of tests/unit/, run_eval.py, run_ci_eval.py, the CI
eval gate). The estimate is the same ballpark providers themselves quote for
"roughly N tokens" copy; good enough for tracking cost trends over time, not
a billing invoice.
ponytail: swap for real usage.input_tokens/output_tokens if per-query cost
ever needs to be exact rather than directional.
"""
from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Any

# USD per 1,000 tokens, input/output. Bedrock Claude Sonnet 4.5 and Haiku 4.5
# on-demand pricing (us-east-1); gpt-4o-mini is what every LLM call site in
# this project falls back to when Bedrock is throttled or unavailable (see
# answer_generator.py's _is_bedrock_unavailable / query_rewriter.py's
# equivalent).
PRICING_PER_1K_TOKENS: dict[str, dict[str, float]] = {
    "sonnet": {"input": 0.003, "output": 0.015},
    "haiku": {"input": 0.001, "output": 0.005},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
}

CHARS_PER_TOKEN = 4  # rough estimate, see module docstring


def estimate_cost_usd(model: str, input_text: str, output_text: str) -> float:
    """Estimate USD cost for one LLM call from input/output text length.

    Args:
        model: One of PRICING_PER_1K_TOKENS' keys ("sonnet", "haiku", or
            "gpt-4o-mini").
        input_text: The prompt sent to the model (system + user combined).
        output_text: The text the model returned.

    Returns:
        Estimated cost in USD. 0.0 for an unrecognized model rather than
        raising -- a pricing-table miss must never crash a query.
    """
    pricing = PRICING_PER_1K_TOKENS.get(model)
    if pricing is None:
        return 0.0
    input_tokens = len(input_text) / CHARS_PER_TOKEN
    output_tokens = len(output_text) / CHARS_PER_TOKEN
    return (input_tokens / 1000) * pricing["input"] + (output_tokens / 1000) * pricing["output"]


def _to_decimal(value: float) -> Decimal:
    """DynamoDB's resource API rejects native float; round first so the
    Decimal conversion doesn't carry float's binary-representation noise."""
    return Decimal(str(round(value, 6)))


def log_query(
    dynamodb_resource: Any,
    table_name: str,
    query: str,
    rewritten_query: str,
    answer: str,
    citations: list[dict[str, Any]],
    cost_usd: float,
    latency_ms_total: int,
    latency_ms_per_stage: dict[str, int],
    user_id: str = "unknown",
) -> None:
    """Write one query's full record to the DynamoDB query-log table.

    Best-effort observability, not a correctness requirement: any failure
    here (throttled table, network blip, IAM misconfig) is swallowed rather
    than raised, so a logging outage never fails the user's actual query.

    Args:
        dynamodb_resource: A boto3 DynamoDB resource (``boto3.resource("dynamodb")``).
        table_name: The query-log table name (``finrag-query-logs``, from
            infra/stacks/storage_stack.py).
        query: The user's original question.
        rewritten_query: The query after query_rewriter.rewrite_query().
        answer: The final (verified) answer text.
        citations: The citations list returned alongside the answer.
        cost_usd: Total estimated cost across every LLM call this query made.
        latency_ms_total: Wall-clock time for the whole pipeline.
        latency_ms_per_stage: e.g. {"rewrite": 210, "retrieve": 340,
            "rerank": 90, "generate": 1800, "verify": 15}.
        user_id: Caller identity, when known (Cognito client_id, or
            "unknown" for the static-token era / local runs).
    """
    try:
        table = dynamodb_resource.Table(table_name)
        table.put_item(Item={
            "query_id": str(uuid.uuid4()),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "query": query,
            "rewritten_query": rewritten_query,
            "answer": answer,
            "n_citations": len(citations),
            "cited_tickers": sorted({c.get("ticker") for c in citations if c.get("ticker")}),
            "cost_usd": _to_decimal(cost_usd),
            "latency_ms_total": latency_ms_total,
            "latency_ms_per_stage": {k: int(v) for k, v in latency_ms_per_stage.items()},
            "user_id": user_id,
        })
    except Exception:
        # Never let observability take down the actual answer.
        pass

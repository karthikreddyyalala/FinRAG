"""Server-wide call limits for the public, no-sign-in endpoint.

Per-caller limits can't work here: Claude's connectors call from Anthropic's
servers, so every visitor arrives from the same few IP addresses. Lambda
can't cap it either: the account's concurrency limit is 10, with nothing
left to reserve. So two shared counters in DynamoDB, per minute and per UTC
day. Changing a limit means a deploy.
"""
from __future__ import annotations

import time
from typing import Any

from botocore.exceptions import ClientError

TABLE = "finrag-rate-limits"
PER_MINUTE = 30
PER_DAY = 1000


class RateLimited(Exception):
    """The shared limit is spent; retry_after is seconds until it resets."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"rate limited; retry in {retry_after}s")
        self.retry_after = retry_after


def check_rate_limit(dynamodb_resource: Any, now: float | None = None) -> None:
    """Count one call against both limits, or raise RateLimited.

    Fails open: if DynamoDB itself errors, the call goes through and the
    fault is printed. A broken counter taking the demo down is the worse
    failure; the monthly budget alarm bounds the cost.
    """
    now = time.time() if now is None else now
    minute = int(now // 60)
    buckets = (
        (f"min#{minute}", PER_MINUTE, (minute + 1) * 60),
        (f"day#{time.strftime('%Y-%m-%d', time.gmtime(now))}", PER_DAY,
         (int(now // 86400) + 1) * 86400),
    )
    try:
        table = dynamodb_resource.Table(TABLE)
        for key, limit, resets_at in buckets:
            try:
                table.update_item(
                    Key={"bucket": key},
                    UpdateExpression="SET expires_at = :expires ADD hits :one",
                    ConditionExpression="attribute_not_exists(hits) OR hits < :limit",
                    ExpressionAttributeValues={
                        ":one": 1, ":limit": limit, ":expires": resets_at + 3600,
                    },
                )
            except ClientError as e:
                if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
                raise RateLimited(max(1, int(resets_at - now))) from None
    except RateLimited:
        raise
    except Exception as exc:
        print(f"finrag: rate limiter unavailable ({type(exc).__name__}); allowing call",
              flush=True)

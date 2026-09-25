"""CloudWatch dashboard for the MCP server Lambda: invocations, errors,
latency, and cost.

"Cost" here is estimated AWS Lambda compute cost (duration x memory x
on-demand price), not per-query LLM spend -- that's already tracked
per-query in DynamoDB (finrag-query-logs, see server/observability/logger.py
and README's "aws dynamodb scan" command). Duplicating it as a custom
CloudWatch metric would mean a PutMetricData call on every query for numbers
this dashboard can't act on any faster than a DynamoDB scan already does.
"""
from __future__ import annotations

from aws_cdk import Duration, Stack
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_lambda as lambda_
from constructs import Construct

# On-demand price for a 2048 MB arm64 Lambda in us-east-1 (matches
# McpServerStack's memory_size + Architecture.ARM_64).
_GB_SECOND_PRICE_USD = 0.0000133334
_MEMORY_GB = 2048 / 1024


class ObservabilityStack(Stack):
    """One dashboard: invocations, errors, p50/p99 duration, estimated cost."""

    def __init__(
        self, scope: Construct, construct_id: str, *, fn: lambda_.IFunction, **kwargs
    ) -> None:
        """Build the dashboard from the deployed Lambda's own metrics.

        Args:
            scope: The parent construct.
            construct_id: Logical ID of this stack within the app.
            fn: The MCP server Lambda (from McpServerStack) to graph.
            **kwargs: Passed through to `Stack.__init__` (e.g. `env`).
        """
        super().__init__(scope, construct_id, **kwargs)

        invocations = fn.metric_invocations(period=Duration.minutes(5))
        errors = fn.metric_errors(period=Duration.minutes(5))
        duration = fn.metric_duration(period=Duration.minutes(5))

        estimated_cost = cloudwatch.MathExpression(
            expression=f"invocations * (duration / 1000) * {_MEMORY_GB} * {_GB_SECOND_PRICE_USD}",
            using_metrics={
                "invocations": fn.metric_invocations(period=Duration.hours(1), statistic="Sum"),
                "duration": fn.metric_duration(period=Duration.hours(1), statistic="Sum"),
            },
            label="Estimated Lambda compute cost (USD/hr)",
            period=Duration.hours(1),
        )

        dashboard = cloudwatch.Dashboard(
            self, "McpServerDashboard", dashboard_name="finrag-mcp-server"
        )
        dashboard.add_widgets(
            cloudwatch.GraphWidget(title="Invocations", left=[invocations], width=8),
            cloudwatch.GraphWidget(title="Errors", left=[errors], width=8),
            cloudwatch.GraphWidget(
                title="Duration (ms)",
                left=[duration.with_(statistic="p50"), duration.with_(statistic="p99")],
                width=8,
            ),
        )
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Estimated Lambda compute cost (USD/hr)", left=[estimated_cost], width=12
            ),
            cloudwatch.TextWidget(
                markdown=(
                    "**Per-query LLM cost** (Bedrock/OpenAI, not shown above) is tracked "
                    "per-row in DynamoDB `finrag-query-logs`, not as a CloudWatch metric -- "
                    "see README's `aws dynamodb scan --table-name finrag-query-logs` command."
                ),
                width=12,
            ),
        )

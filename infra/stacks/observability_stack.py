"""CloudWatch dashboard for the MCP server Lambda: invocations, errors,
latency, and cost.

"Cost" here is estimated AWS Lambda compute cost (duration x memory x
on-demand price). The server runs no chat model, so there is no LLM spend to
show; per-call records go to DynamoDB (finrag-query-logs, written by
server/observability/call_log.py) and to `finrag_call` CloudWatch log lines
(query them with Logs Insights). Duplicating them as a custom
CloudWatch metric would mean a PutMetricData call on every query for numbers
this dashboard can't act on any faster than a DynamoDB scan already does.
"""
from __future__ import annotations

from aws_cdk import Duration, Stack
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from constructs import Construct

# On-demand price for a 2048 MB arm64 Lambda in us-east-1 (matches
# McpServerStack's memory_size + Architecture.ARM_64).
_GB_SECOND_PRICE_USD = 0.0000133334
_MEMORY_GB = 2048 / 1024


class ObservabilityStack(Stack):
    """One dashboard: invocations, errors, p50/p99 duration, estimated cost."""

    def __init__(
        self, scope: Construct, construct_id: str, *, fn: lambda_.IFunction,
        refresh_fn: lambda_.IFunction, **kwargs
    ) -> None:
        """Build the dashboard from the deployed Lambda's own metrics.

        Args:
            scope: The parent construct.
            construct_id: Logical ID of this stack within the app.
            fn: The MCP server Lambda (from McpServerStack) to graph.
            refresh_fn: The weekly refresh Lambda (from IngestionStack), alarmed on any error.
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
                    "**Per-call records** (the server runs no chat model, so no LLM cost) go to "
                    "DynamoDB `finrag-query-logs` and to `finrag_call` lines in the "
                    "server log group; query them with Logs Insights."
                ),
                width=12,
            ),
        )

        # Nothing alerted anyone while the weekly refresh failed every run for
        # a month (2026-09-30 to 10-28), or when OpenAI ran out of credits.
        topic = sns.Topic(self, "AlertsTopic", topic_name="finrag-alerts")
        # cdk deploy -c alert_email=you@example.com; never committed.
        email = self.node.try_get_context("alert_email")
        if email:
            topic.add_subscription(subs.EmailSubscription(email))

        server_errors = cloudwatch.Alarm(
            self, "McpServerErrors",
            alarm_name="finrag-mcp-server-errors",
            # The 5-minute health check fails 3 times in 15 minutes when
            # retrieval is down; one stray visitor error does not page.
            metric=fn.metric_errors(period=Duration.minutes(15), statistic="Sum"),
            threshold=3,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        refresh_errors = cloudwatch.Alarm(
            self, "RefreshErrors",
            alarm_name="finrag-weekly-refresh-errors",
            metric=refresh_fn.metric_errors(period=Duration.hours(1), statistic="Sum"),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        for alarm in (server_errors, refresh_errors):
            alarm.add_alarm_action(cw_actions.SnsAction(topic))

        if email:
            # A public URL can be hammered: 10 concurrent instances nonstop is
            # about $30/day. Email at 80% of $10/month actual spend.
            budgets.CfnBudget(
                self, "MonthlyBudget",
                budget=budgets.CfnBudget.BudgetDataProperty(
                    budget_name="finrag-monthly", budget_type="COST", time_unit="MONTHLY",
                    budget_limit=budgets.CfnBudget.SpendProperty(amount=10, unit="USD"),
                ),
                notifications_with_subscribers=[
                    budgets.CfnBudget.NotificationWithSubscribersProperty(
                        notification=budgets.CfnBudget.NotificationProperty(
                            notification_type="ACTUAL", comparison_operator="GREATER_THAN",
                            threshold=80, threshold_type="PERCENTAGE",
                        ),
                        subscribers=[budgets.CfnBudget.SubscriberProperty(
                            subscription_type="EMAIL", address=email,
                        )],
                    )
                ],
            )

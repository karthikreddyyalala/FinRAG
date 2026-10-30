"""Unit tests for ObservabilityStack: the CloudWatch dashboard."""
import aws_cdk as cdk
from aws_cdk.assertions import Template

from infra.stacks.ingestion_stack import IngestionStack
from infra.stacks.mcp_server_stack import McpServerStack
from infra.stacks.observability_stack import ObservabilityStack


def _template(context=None) -> Template:
    app = cdk.App(context={"aws:cdk:bundling-stacks": [], **(context or {})})
    env = cdk.Environment(account="123456789012", region="us-east-1")
    server_stack = McpServerStack(app, "TestMcpServerStack", env=env)
    ingestion_stack = IngestionStack(app, "TestIngestionStack", env=env)
    obs_stack = ObservabilityStack(app, "TestObservabilityStack", fn=server_stack.fn,
                                   refresh_fn=ingestion_stack.fn, env=env)
    return Template.from_stack(obs_stack)


def test_dashboard_created_with_fixed_name():
    _template().has_resource_properties("AWS::CloudWatch::Dashboard", {
        "DashboardName": "finrag-mcp-server",
    })


def test_dashboard_graphs_invocations_errors_duration_and_cost():
    body = _template().find_resources("AWS::CloudWatch::Dashboard")
    dashboard_json = next(iter(body.values()))["Properties"]["DashboardBody"]
    # DashboardBody is a CFN intrinsic (Fn::Join), so just check the widget
    # titles are present in the raw JSON fragments it's built from.
    flattened = str(dashboard_json)
    for title in ("Invocations", "Errors", "Duration", "Estimated Lambda compute cost"):
        assert title in flattened, f"missing widget: {title}"


def test_alarms_on_server_errors_and_on_any_refresh_failure():
    alarms = _template().find_resources("AWS::CloudWatch::Alarm")
    by_name = {a["Properties"]["AlarmName"]: a["Properties"] for a in alarms.values()}
    assert by_name["finrag-mcp-server-errors"]["Threshold"] == 3
    assert by_name["finrag-weekly-refresh-errors"]["Threshold"] == 1
    for props in by_name.values():
        assert props["AlarmActions"], "alarm notifies nobody"


def test_email_and_budget_only_when_an_address_is_given():
    assert not _template().find_resources("AWS::SNS::Subscription")
    assert not _template().find_resources("AWS::Budgets::Budget")
    with_email = _template({"alert_email": "owner@example.com"})
    with_email.has_resource_properties("AWS::SNS::Subscription", {"Protocol": "email"})
    with_email.has_resource_properties("AWS::Budgets::Budget", {
        "Budget": {"BudgetLimit": {"Amount": 10, "Unit": "USD"}, "TimeUnit": "MONTHLY",
                   "BudgetType": "COST"},
    })

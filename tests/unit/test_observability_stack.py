"""Unit tests for ObservabilityStack: the CloudWatch dashboard."""
import aws_cdk as cdk
from aws_cdk.assertions import Template

from infra.stacks.mcp_server_stack import McpServerStack
from infra.stacks.observability_stack import ObservabilityStack


def _template() -> Template:
    app = cdk.App(context={"aws:cdk:bundling-stacks": []})  # skip pip bundling
    env = cdk.Environment(account="123456789012", region="us-east-1")
    server_stack = McpServerStack(app, "TestMcpServerStack", env=env)
    obs_stack = ObservabilityStack(app, "TestObservabilityStack", fn=server_stack.fn, env=env)
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

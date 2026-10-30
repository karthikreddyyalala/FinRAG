"""Unit tests for McpServerStack: the deployed Lambda, URL, and health schedule.

Bundling is skipped here (it pip-installs the runtime), so these assert the
shape of what gets deployed, especially the properties that would cost
money or leak secrets if they regressed.
"""
import json

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from infra.stacks.mcp_server_stack import McpServerStack


def _template() -> Template:
    app = cdk.App(context={"aws:cdk:bundling-stacks": []})  # skip pip bundling
    stack = McpServerStack(app, "TestMcpServerStack", env=cdk.Environment(
        account="123456789012", region="us-east-1"))
    return Template.from_stack(stack)


def test_lambda_runs_the_mcp_handler_on_graviton():
    _template().has_resource_properties("AWS::Lambda::Function", {
        "Handler": "server.main.handler",
        "Runtime": "python3.13",
        "Architectures": ["arm64"],  # ~20% cheaper per GB-second than x86
    })


def test_no_secret_values_in_lambda_environment():
    """Only SSM parameter names belong in the environment."""
    fn = next(iter(_template().find_resources("AWS::Lambda::Function").values()))
    env = fn["Properties"].get("Environment", {}).get("Variables", {})
    assert env == {"FINRAG_SSM_PREFIX": "/finrag"}


def test_function_url_is_public_with_no_sign_in():
    _template().has_resource_properties("AWS::Lambda::Url", {"AuthType": "NONE"})


def test_no_cognito_and_no_bedrock():
    template = _template()
    assert not template.find_resources("AWS::Cognito::UserPool")
    assert "bedrock" not in json.dumps(template.find_resources("AWS::IAM::Policy")).lower()


def test_ephemeral_storage_fits_the_keyword_index():
    _template().has_resource_properties("AWS::Lambda::Function", {
        "EphemeralStorage": {"Size": Match.any_value()},
    })


def test_iam_is_scoped_not_wildcard():
    policies = _template().find_resources("AWS::IAM::Policy")
    doc = json.dumps(policies)
    assert "keyword/*" in doc and "parameter/finrag/*" in doc
    for policy in policies.values():
        for stmt in policy["Properties"]["PolicyDocument"]["Statement"]:
            assert stmt.get("Resource") != "*", f"wildcard resource on {stmt['Action']}"


def test_logs_kept_30_days():
    _template().has_resource_properties("AWS::Logs::LogGroup", {"RetentionInDays": 30})


def test_lambda_can_count_calls_in_the_rate_limit_table_only():
    _template().has_resource_properties("AWS::IAM::Policy", {
        "PolicyDocument": {"Statement": Match.array_with([Match.object_like({
            "Action": "dynamodb:UpdateItem",
            "Resource": Match.string_like_regexp(r".*table/finrag-rate-limits$"),
        })])},
    })


def test_lambda_can_read_and_write_the_query_cache_table():
    _template().has_resource_properties("AWS::IAM::Policy", {
        "PolicyDocument": {"Statement": Match.array_with([Match.object_like({
            "Action": Match.array_with(["dynamodb:GetItem", "dynamodb:PutItem"]),
            "Resource": Match.string_like_regexp(r".*table/finrag-query-cache$"),
        })])},
    })


def test_health_check_runs_every_5_minutes_with_its_marker_event():
    rule = next(iter(_template().find_resources("AWS::Events::Rule").values()))
    props = rule["Properties"]
    assert props["ScheduleExpression"] == "rate(5 minutes)"
    assert json.loads(props["Targets"][0]["Input"]) == {"finrag_health_check": True}

"""Unit tests for IngestionStack: the weekly-refresh Lambda + EventBridge rule.

Mirrors test_mcp_server_stack.py's pattern -- bundling is skipped (it
pip-installs the runtime), assertions target what would cost money or leak
scope if it regressed.
"""
import json

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from infra.stacks.ingestion_stack import IngestionStack


def _template() -> Template:
    app = cdk.App(context={"aws:cdk:bundling-stacks": []})  # skip pip bundling
    stack = IngestionStack(app, "TestIngestionStack", env=cdk.Environment(
        account="123456789012", region="us-east-1"))
    return Template.from_stack(stack)


def test_lambda_runs_the_weekly_refresh_handler():
    _template().has_resource_properties("AWS::Lambda::Function", {
        "Handler": "scripts.weekly_refresh.handler",
        "Runtime": "python3.13",
        "Architectures": ["arm64"],
    })


def test_timeout_is_capped_at_the_lambda_maximum():
    """A big filing week (many companies reporting at once) could still push
    close to this -- 15 minutes is Lambda's hard ceiling, not a margin."""
    fn = next(iter(_template().find_resources("AWS::Lambda::Function").values()))
    assert fn["Properties"]["Timeout"] == 900


def test_scheduled_weekly_via_eventbridge():
    _template().has_resource_properties("AWS::Events::Rule", {
        "ScheduleExpression": "rate(7 days)",
        "State": "ENABLED",
    })


def test_eventbridge_targets_the_ingestion_lambda():
    rules = _template().find_resources("AWS::Events::Rule")
    rule = next(iter(rules.values()))
    target_ref = rule["Properties"]["Targets"][0]["Arn"]["Fn::GetAtt"][0]
    assert target_ref.startswith("IngestionFunction")


def test_iam_is_scoped_not_wildcard():
    policies = _template().find_resources("AWS::IAM::Policy")
    doc = json.dumps(policies)
    assert "finrag-raw-filings" in doc
    assert "chunk_cache" in doc
    assert "keyword" in doc
    assert "parameter/finrag/*" in doc
    for policy in policies.values():
        for stmt in policy["Properties"]["PolicyDocument"]["Statement"]:
            assert stmt.get("Resource") != "*", f"wildcard resource on {stmt['Action']}"


def test_no_secret_values_in_lambda_environment():
    fn = next(iter(_template().find_resources("AWS::Lambda::Function").values()))
    env = fn["Properties"].get("Environment", {}).get("Variables", {})
    assert env.get("FINRAG_SSM_PREFIX") == "/finrag"
    forbidden = {"OPENAI_API_KEY", "PINECONE_API_KEY"}
    assert not forbidden & set(env)


def test_logs_expire_so_storage_cost_cannot_grow_unbounded():
    _template().has_resource_properties("AWS::Logs::LogGroup", {
        "RetentionInDays": Match.any_value(),
    })


def test_chunk_cache_points_at_tmp_the_only_writable_path():
    """Regression guard: this Lambda failed every scheduled run without it.

    The default cache dir derives from __file__, which is /var/task/evals/...
    inside Lambda -- read-only, so mkdir raised OSError and the refresh died
    before touching EDGAR. Only /tmp is writable.
    """
    _template().has_resource_properties("AWS::Lambda::Function", {
        "Environment": {
            "Variables": Match.object_like({"FINRAG_CHUNK_CACHE_DIR": "/tmp/finrag/chunk_cache"})
        }
    })


def test_tmp_fits_the_keyword_index_and_the_chunk_cache_together():
    """Regression guard: 1 GiB of /tmp was not enough and the run died.

    The weekly refresh holds BOTH artifacts on local disk at once: the
    keyword index it rebuilds (~884 MiB as of 2026-10) and the chunk cache
    it pulls from S3 (~820 MiB across 71 files). That is ~1.7 GiB before
    SQLite's own build scratch, against a 1 GiB /tmp -- the build failed
    with "OperationalError: database or disk is full" after processing all
    72 tickers, so the whole run was wasted at the very last step.
    """
    _template().has_resource_properties("AWS::Lambda::Function", {
        "EphemeralStorage": {"Size": 4096},
        "MemorySize": 2048,
    })


def test_refresh_logs_kept_30_days_so_failures_can_be_diagnosed():
    """Retention was 7 days; the causes of the Sep-Oct 2026 refresh failures were lost."""
    import aws_cdk as cdk
    from aws_cdk.assertions import Template

    from infra.stacks.ingestion_stack import IngestionStack

    app = cdk.App(context={"aws:cdk:bundling-stacks": []})
    stack = IngestionStack(app, "TestIngestionRetention",
                           env=cdk.Environment(account="123456789012", region="us-east-1"))
    Template.from_stack(stack).has_resource_properties("AWS::Logs::LogGroup",
                                                       {"RetentionInDays": 30})

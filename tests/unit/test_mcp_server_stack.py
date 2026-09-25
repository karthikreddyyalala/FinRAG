"""Unit tests for McpServerStack: the deployed Lambda + Function URL.

Bundling is skipped here (it pip-installs the runtime), so these assert the
shape of what gets deployed -- especially the properties that would cost
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
    """Only SSM parameter names belong in the environment -- values in env
    vars would sit in plaintext in the CloudFormation template."""
    fn = next(iter(_template().find_resources("AWS::Lambda::Function").values()))
    env = fn["Properties"].get("Environment", {}).get("Variables", {})
    assert env.get("FINRAG_SSM_PREFIX") == "/finrag"
    forbidden = {"OPENAI_API_KEY", "PINECONE_API_KEY", "MCP_AUTH_TOKEN"}
    assert not forbidden & set(env), f"secret in plaintext env: {forbidden & set(env)}"


def test_function_url_is_public_because_auth_is_in_the_app():
    """AWS_IAM auth would need SigV4, which MCP clients cannot send; the
    handler enforces a bearer token before any work instead."""
    _template().has_resource_properties("AWS::Lambda::Url", {"AuthType": "NONE"})


def test_ephemeral_storage_fits_the_keyword_index():
    """The ~900 MB index is downloaded to /tmp; the 512 MB default can't hold it."""
    _template().has_resource_properties("AWS::Lambda::Function", {
        "EphemeralStorage": {"Size": Match.any_value()},
    })
    fn = next(iter(_template().find_resources("AWS::Lambda::Function").values()))
    assert fn["Properties"]["EphemeralStorage"]["Size"] >= 1536


def test_iam_is_scoped_not_wildcard():
    """The function may read the keyword index and /finrag parameters only."""
    policies = _template().find_resources("AWS::IAM::Policy")
    doc = json.dumps(policies)
    assert "keyword/*" in doc, "S3 read not scoped to the keyword index"
    assert "parameter/finrag/*" in doc, "SSM read not scoped to /finrag"
    for policy in policies.values():
        for stmt in policy["Properties"]["PolicyDocument"]["Statement"]:
            assert stmt.get("Resource") != "*", f"wildcard resource on {stmt['Action']}"


def test_logs_expire_so_storage_cost_cannot_grow_unbounded():
    _template().has_resource_properties("AWS::Logs::LogGroup", {
        "RetentionInDays": Match.any_value(),
    })


def test_cognito_user_pool_has_no_self_signup():
    """This is a single-user personal deployment -- the one Cognito user is
    created by an admin CLI call, not a public sign-up form."""
    _template().has_resource_properties("AWS::Cognito::UserPool", {
        "AdminCreateUserConfig": {"AllowAdminCreateUserOnly": True},
    })


def test_cognito_app_client_is_public_with_pkce_auth_code_flow():
    """No client secret: PKCE (RFC 7636) is what secures a public client's
    authorization_code flow instead, which is what CLAUDE.md's Phase 3 spec
    calls for and what mcp-remote's OAuth discovery expects."""
    _template().has_resource_properties("AWS::Cognito::UserPoolClient", {
        "GenerateSecret": False,
        "AllowedOAuthFlows": ["code"],
        "AllowedOAuthFlowsUserPoolClient": True,
    })


def test_cognito_resource_server_defines_the_invoke_scope():
    _template().has_resource_properties("AWS::Cognito::UserPoolResourceServer", {
        "Identifier": "finrag",
        "Scopes": Match.array_with([Match.object_like({"ScopeName": "invoke"})]),
    })


def test_cognito_hosted_domain_exists():
    _template().has_resource_properties("AWS::Cognito::UserPoolDomain", {
        "Domain": Match.any_value(),
    })


def test_lambda_env_has_cognito_ids_but_no_secrets():
    """User pool ID and client ID are not secrets (they're visible in any
    OAuth discovery response) -- fine in plaintext env, unlike the API keys
    in test_no_secret_values_in_lambda_environment above."""
    fn = next(iter(_template().find_resources("AWS::Lambda::Function").values()))
    env = fn["Properties"].get("Environment", {}).get("Variables", {})
    assert "COGNITO_USER_POOL_ID" in env
    assert "COGNITO_CLIENT_ID" in env


def test_lambda_can_read_and_write_the_query_cache_table_only():
    """Phase C4: the cache is read+write (unlike the write-only log table),
    and scoped to exactly the cache table's ARN, not a wildcard."""
    _template().has_resource_properties("AWS::IAM::Policy", {
        "PolicyDocument": {
            "Statement": Match.array_with([
                Match.object_like({
                    "Action": Match.array_with(["dynamodb:GetItem", "dynamodb:PutItem"]),
                    "Resource": Match.string_like_regexp(r".*table/finrag-query-cache$"),
                })
            ]),
        },
    })

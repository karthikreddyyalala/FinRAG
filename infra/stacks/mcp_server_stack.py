"""Lambda + Function URL serving the FinRAG MCP server.

Function URL rather than API Gateway: API Gateway caps integrations at 29 s,
and a cold start downloads the ~900 MB keyword index before answering.
Bundling runs pip locally for the Lambda platform (no Docker needed), and
installs only the server's runtime dependencies -- not pandas, torch, or the
eval stack.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsii
from aws_cdk import BundlingOptions, CfnOutput, Duration, ILocalBundling, Size, Stack
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

# mcp-remote derives a stable local callback port from a hash of the server
# URL (not a fixed default) -- verified live for this exact Function URL by
# running mcp-remote directly and reading "Using callback port derived from
# the server URL: 11164" from its own log. A mismatch here fails silently in
# Cognito's hosted UI ("An error was encountered with the requested page"),
# not with any error naming the redirect_uri.
OAUTH_CALLBACK_URL = "http://localhost:11164/oauth/callback"

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PACKAGES = ("server", "pipeline")
# boto3 is omitted: the Lambda runtime provides it.
RUNTIME_REQUIREMENTS = (
    "fastapi>=0.115,<1.0",
    "mangum>=0.19,<1.0",
    "mcp>=2.0,<3.0",
    "pinecone>=8.0,<9.0",
    "openai>=1.50,<3.0",
    "requests>=2.31,<3.0",
    "pyjwt[crypto]>=2.9,<3.0",
)
PYTHON_VERSION = "3.13"


@jsii.implements(ILocalBundling)
class _LocalPipBundling:
    """Build the deployment package with pip, no Docker required."""

    def try_bundle(self, output_dir: str, *, image: Any = None, **_: Any) -> bool:
        """Install ARM64 wheels and copy the source packages into output_dir."""
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "--target", output_dir,
             "--platform", "manylinux2014_aarch64", "--implementation", "cp",
             "--python-version", PYTHON_VERSION, "--only-binary=:all:",
             *RUNTIME_REQUIREMENTS],
            check=True,
        )
        for package in SOURCE_PACKAGES:
            shutil.copytree(
                REPO_ROOT / package,
                Path(output_dir) / package,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        return True


class McpServerStack(Stack):
    """The MCP server: one Lambda behind a public Function URL."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs: Any) -> None:
        """Define the Lambda, its permissions, and its URL.

        Args:
            scope: The parent construct.
            construct_id: Logical ID of this stack within the app.
            **kwargs: Passed through to `Stack.__init__` (e.g. `env`).
        """
        super().__init__(scope, construct_id, **kwargs)

        runtime = lambda_.Runtime.PYTHON_3_13
        code = lambda_.Code.from_asset(
            str(REPO_ROOT),
            # Fingerprint only the source that ships; the repo root also holds
            # ~2 GB of cached chunks and indexes that must not be hashed.
            exclude=[
                "*",
                *(f"!{p}" for p in SOURCE_PACKAGES),
                *(f"!{p}/**" for p in SOURCE_PACKAGES),
                "**/__pycache__",
                "**/*.pyc",
            ],
            bundling=BundlingOptions(
                image=runtime.bundling_image,  # unused: local bundling succeeds
                local=_LocalPipBundling(),
                command=["bash", "-c", "echo 'local bundling expected' && exit 1"],
            ),
        )

        log_group = logs.LogGroup(
            self, "McpServerLogs", retention=logs.RetentionDays.ONE_WEEK
        )

        # Single-user personal deployment: no public sign-up, the one user is
        # created via `aws cognito-idp admin-create-user`.
        user_pool = cognito.UserPool(
            self, "McpUserPool",
            user_pool_name="finrag-mcp-users",
            self_sign_up_enabled=False,
        )
        user_pool.add_domain(
            "McpUserPoolDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"finrag-mcp-{self.account}"
            ),
        )
        invoke_scope = cognito.ResourceServerScope(
            scope_name="invoke", scope_description="Call FinRAG MCP tools"
        )
        resource_server = user_pool.add_resource_server(
            "McpResourceServer", identifier="finrag", scopes=[invoke_scope]
        )
        # generate_secret=False + authorization_code_grant only: a public
        # client, secured by PKCE (RFC 7636) instead of a client secret --
        # required because an MCP client like mcp-remote cannot keep a
        # secret confidential.
        app_client = user_pool.add_client(
            "McpAppClient",
            generate_secret=False,
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                # mcp-remote's default authorize request always asks for the
                # standard OIDC scopes alongside whatever the server needs --
                # Cognito rejects the whole request (invalid_scope) if any
                # requested scope isn't explicitly allowed for this client,
                # caught live as "Authorization failed: invalid_request -
                # invalid_scope" with only the custom scope allowed.
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PHONE,
                    cognito.OAuthScope.PROFILE,
                    cognito.OAuthScope.resource_server(resource_server, invoke_scope),
                ],
                callback_urls=[OAUTH_CALLBACK_URL],
            ),
        )

        fn = lambda_.Function(
            self,
            "McpServerFunction",
            function_name="finrag-mcp-server",
            runtime=runtime,
            architecture=lambda_.Architecture.ARM_64,
            handler="server.main.handler",
            code=code,
            memory_size=2048,  # CPU scales with memory; speeds the index download
            ephemeral_storage_size=Size.mebibytes(2048),  # /tmp holds the ~900 MB index
            timeout=Duration.minutes(2),
            environment={
                "FINRAG_SSM_PREFIX": "/finrag",  # names only, never values
                # Not secrets: both are visible in any OAuth discovery response.
                "COGNITO_USER_POOL_ID": user_pool.user_pool_id,
                "COGNITO_CLIENT_ID": app_client.user_pool_client_id,
            },
            log_group=log_group,
        )

        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=["arn:aws:s3:::finrag-processed-filings/keyword/*"],
        ))
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["ssm:GetParameters"],
            resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter/finrag/*"],
        ))
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=[
                "arn:aws:bedrock:*::foundation-model/anthropic.*",
                f"arn:aws:bedrock:*:{self.account}:inference-profile/us.anthropic.*",
            ],
        ))
        # Per-query cost/latency logging (Phase C, CLAUDE.md). Table itself
        # lives in StorageStack; referenced by name here rather than a CDK
        # cross-stack construct import, matching how PROCESSED_BUCKET is
        # already a hardcoded name constant in server/main.py, not a passed
        # reference. Write-only: this Lambda never needs to read its own logs.
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["dynamodb:PutItem"],
            resources=[f"arn:aws:dynamodb:{self.region}:{self.account}:table/finrag-query-logs"],
        ))

        url = fn.add_function_url(auth_type=lambda_.FunctionUrlAuthType.NONE)
        CfnOutput(self, "McpEndpoint", value=f"{url.url}mcp")
        CfnOutput(self, "CognitoUserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "CognitoClientId", value=app_client.user_pool_client_id)
        CfnOutput(
            self, "CognitoAuthorizeUrl",
            value=f"https://finrag-mcp-{self.account}.auth.{self.region}.amazoncognito.com",
        )

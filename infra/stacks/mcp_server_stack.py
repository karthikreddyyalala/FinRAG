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
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

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
            environment={"FINRAG_SSM_PREFIX": "/finrag"},  # names only, never values
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

        url = fn.add_function_url(auth_type=lambda_.FunctionUrlAuthType.NONE)
        CfnOutput(self, "McpEndpoint", value=f"{url.url}mcp")

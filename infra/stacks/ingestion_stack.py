"""EventBridge weekly cron: ingestion Lambda running scripts/weekly_refresh.py.

Same no-Docker local-pip-bundling as McpServerStack, but with the ingestion
deps (pandas, lxml, beautifulsoup4, tiktoken) that Lambda deliberately
excludes to stay small -- this one only needs to fit under the 250 MB zip
limit once, not be small for cold-start latency the way a user-facing
request is.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsii
from aws_cdk import BundlingOptions, Duration, ILocalBundling, Size, Stack
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from constructs import Construct

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PACKAGES = ("server", "pipeline", "scripts")
RAW_BUCKET = "finrag-raw-filings"
PROCESSED_BUCKET = "finrag-processed-filings"
# boto3 is omitted: the Lambda runtime provides it.
RUNTIME_REQUIREMENTS = (
    "beautifulsoup4>=4.12,<5.0",
    "lxml>=5.0,<6.0",
    "pandas>=2.2,<3.0",
    "pinecone>=8.0,<9.0",
    "openai>=1.50,<3.0",
    "tiktoken>=0.7,<1.0",
    "requests>=2.31,<3.0",
)
PYTHON_VERSION = "3.13"


@jsii.implements(ILocalBundling)
class _LocalPipBundling:
    """Build the deployment package with pip, no Docker required."""

    def try_bundle(self, output_dir: str, *, image: Any = None, **_: Any) -> bool:
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


class IngestionStack(Stack):
    """Weekly corpus refresh: one Lambda, triggered by an EventBridge rule."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs: Any) -> None:
        super().__init__(scope, construct_id, **kwargs)

        runtime = lambda_.Runtime.PYTHON_3_13
        code = lambda_.Code.from_asset(
            str(REPO_ROOT),
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
            self, "IngestionLogs", retention=logs.RetentionDays.ONE_WEEK
        )

        fn = lambda_.Function(
            self,
            "IngestionFunction",
            function_name="finrag-weekly-refresh",
            runtime=runtime,
            architecture=lambda_.Architecture.ARM_64,
            handler="scripts.weekly_refresh.handler",
            code=code,
            memory_size=1024,
            ephemeral_storage_size=Size.mebibytes(1024),  # downloaded filings + chunk cache in /tmp
            # Lambda's hard maximum, not a margin: a week where many
            # companies file simultaneously (earnings season) could still
            # exceed it. Known, accepted limitation for personal-scale use --
            # a timeout there is a safe no-op, not data loss: refresh_ticker
            # writes nothing to a ticker's cache until that ticker fully
            # succeeds, and the next week's run just picks up where this one
            # left off.
            timeout=Duration.minutes(15),
            environment={"FINRAG_SSM_PREFIX": "/finrag"},  # names only, never values
            log_group=log_group,
        )

        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:PutObject"],
            resources=[f"arn:aws:s3:::{RAW_BUCKET}/*"],
        ))
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:GetObject", "s3:PutObject"],
            resources=[
                f"arn:aws:s3:::{PROCESSED_BUCKET}/chunk_cache/*",
                f"arn:aws:s3:::{PROCESSED_BUCKET}/keyword/*",
            ],
        ))
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:ListBucket"],
            resources=[f"arn:aws:s3:::{PROCESSED_BUCKET}"],
            conditions={"StringLike": {"s3:prefix": "chunk_cache/*"}},
        ))
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["ssm:GetParameters"],
            resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter/finrag/*"],
        ))

        rule = events.Rule(
            self, "WeeklyRefreshSchedule",
            schedule=events.Schedule.rate(Duration.days(7)),
        )
        rule.add_target(targets.LambdaFunction(fn))

"""S3 buckets and DynamoDB table for raw/processed filings and query logs."""
from __future__ import annotations

from typing import Any

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from constructs import Construct


class StorageStack(Stack):
    """Storage layer: raw filings, processed filings, and query log table."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs: Any) -> None:
        """Define the storage resources.

        Args:
            scope: The parent construct.
            construct_id: Logical ID of this stack within the app.
            **kwargs: Passed through to `Stack.__init__` (e.g. `env`).
        """
        super().__init__(scope, construct_id, **kwargs)

        self.raw_bucket = s3.Bucket(
            self,
            "RawFilingsBucket",
            bucket_name="finrag-raw-filings",
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        self.processed_bucket = s3.Bucket(
            self,
            "ProcessedFilingsBucket",
            bucket_name="finrag-processed-filings",
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        self.query_log_table = dynamodb.Table(
            self,
            "QueryLogTable",
            table_name="finrag-query-logs",
            partition_key=dynamodb.Attribute(
                name="query_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

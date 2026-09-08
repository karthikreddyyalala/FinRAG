"""Unit tests for StorageStack: verifies S3 buckets and DynamoDB table are created."""
import aws_cdk as cdk
from aws_cdk.assertions import Template

from infra.stacks.storage_stack import StorageStack


def test_storage_stack_creates_two_buckets_and_one_table():
    app = cdk.App()
    stack = StorageStack(app, "TestStorageStack")
    template = Template.from_stack(stack)

    template.resource_count_is("AWS::S3::Bucket", 2)
    template.resource_count_is("AWS::DynamoDB::Table", 1)
    template.has_resource_properties(
        "AWS::S3::Bucket", {"BucketName": "finrag-raw-filings"}
    )
    template.has_resource_properties(
        "AWS::S3::Bucket", {"BucketName": "finrag-processed-filings"}
    )
    template.has_resource_properties(
        "AWS::DynamoDB::Table", {"TableName": "finrag-query-logs"}
    )

"""Unit tests for StorageStack: verifies S3 buckets and DynamoDB table are created."""
import aws_cdk as cdk
from aws_cdk.assertions import Template

from infra.stacks.storage_stack import StorageStack


def test_storage_stack_creates_two_buckets_and_three_tables():
    app = cdk.App()
    stack = StorageStack(app, "TestStorageStack")
    template = Template.from_stack(stack)

    template.resource_count_is("AWS::S3::Bucket", 2)
    template.resource_count_is("AWS::DynamoDB::Table", 3)
    template.has_resource_properties(
        "AWS::S3::Bucket", {"BucketName": "finrag-raw-filings"}
    )
    template.has_resource_properties(
        "AWS::S3::Bucket", {"BucketName": "finrag-processed-filings"}
    )
    template.has_resource_properties(
        "AWS::DynamoDB::Table", {"TableName": "finrag-query-logs"}
    )


def test_storage_stack_query_cache_table_has_ttl_and_is_destroyable():
    """Phase C4: cache content is disposable (DESTROY, unlike the log
    table's RETAIN) and expires itself via the `ttl` attribute."""
    app = cdk.App()
    stack = StorageStack(app, "TestStorageStack")
    template = Template.from_stack(stack)

    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "finrag-query-cache",
            "TimeToLiveSpecification": {"AttributeName": "ttl", "Enabled": True},
        },
    )
    template.has_resource(
        "AWS::DynamoDB::Table",
        {"DeletionPolicy": "Delete", "Properties": {"TableName": "finrag-query-cache"}},
    )


def test_rate_limit_table_expires_its_counters():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template

    from infra.stacks.storage_stack import StorageStack

    template = Template.from_stack(StorageStack(cdk.App(), "TestStorageForRateLimits"))
    template.has_resource_properties("AWS::DynamoDB::Table", {
        "TableName": "finrag-rate-limits",
        "KeySchema": [{"AttributeName": "bucket", "KeyType": "HASH"}],
        "TimeToLiveSpecification": {"AttributeName": "expires_at", "Enabled": True},
        "BillingMode": "PAY_PER_REQUEST",
    })


def test_query_logs_expire_via_ttl():
    app = cdk.App()
    template = Template.from_stack(StorageStack(app, "TtlStack"))
    template.has_resource_properties("AWS::DynamoDB::Table", {
        "TableName": "finrag-query-logs",
        "TimeToLiveSpecification": {"AttributeName": "expires_at", "Enabled": True},
    })

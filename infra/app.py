"""CDK app entry point for FinRAG MCP infrastructure."""
import aws_cdk as cdk

from infra.stacks.storage_stack import StorageStack

app = cdk.App()
StorageStack(app, "FinragStorageStack")
app.synth()

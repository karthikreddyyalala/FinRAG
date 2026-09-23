"""CDK app entry point for FinRAG MCP infrastructure."""
import aws_cdk as cdk

from infra.stacks.ingestion_stack import IngestionStack
from infra.stacks.mcp_server_stack import McpServerStack
from infra.stacks.storage_stack import StorageStack

env = cdk.Environment(region="us-east-1")
app = cdk.App()
StorageStack(app, "FinragStorageStack")
McpServerStack(app, "FinragMcpServerStack", env=env)
IngestionStack(app, "FinragIngestionStack", env=env)
app.synth()

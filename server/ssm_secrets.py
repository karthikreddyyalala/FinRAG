"""SSM Parameter Store secret loading, shared by every Lambda in this project.

Split out of server/main.py so scripts/weekly_refresh.py (the ingestion
Lambda) can reuse it without importing FastAPI/MCP/Mangum, none of which it
needs.
"""
from __future__ import annotations

import os
from typing import Any

# SSM parameter name (under the prefix) -> environment variable it populates.
SECRET_PARAMETERS = {
    "openai-api-key": "OPENAI_API_KEY",
    "pinecone-api-key": "PINECONE_API_KEY",
    "mcp-auth-token": "MCP_AUTH_TOKEN",
}


def load_secrets_from_ssm(ssm_client: Any, prefix: str) -> None:
    """Populate secret environment variables from SSM SecureString parameters.

    The Lambda carries only parameter *names*; values never appear in code or
    in the CloudFormation template. A variable already set in the environment
    wins, so local dev and the eval harness keep working without SSM.

    Args:
        ssm_client: A boto3 SSM client.
        prefix: Parameter path prefix, e.g. "/finrag".

    Raises:
        RuntimeError: If a needed parameter is missing -- better to fail the
            cold start than to surface later as a vague auth error.
    """
    needed = {
        f"{prefix}/{param}": env_var
        for param, env_var in SECRET_PARAMETERS.items()
        if not os.environ.get(env_var)
    }
    if not needed:
        return
    resp = ssm_client.get_parameters(Names=list(needed), WithDecryption=True)
    if resp.get("InvalidParameters"):
        raise RuntimeError(f"SSM parameters missing: {sorted(resp['InvalidParameters'])}")
    for param in resp["Parameters"]:
        os.environ[needed[param["Name"]]] = param["Value"]

"""TDD: secrets come from SSM Parameter Store at cold start, never from code.

CLAUDE.md Phase 8 forbids hardcoded credentials. Lambda environment
variables would put the keys in plaintext in the CloudFormation template, so
the Lambda carries only parameter *names* and resolves the values at runtime.
SSM standard SecureString parameters are free, unlike Secrets Manager.
"""
from unittest.mock import MagicMock, patch

from server.main import SECRET_PARAMETERS, load_secrets_from_ssm


def _ssm_returning(values: dict[str, str]):
    """Fake that honours the real contract: only the requested Names come back."""

    def get_parameters(Names, WithDecryption):  # noqa: N803 - boto3's kwarg names
        return {
            "Parameters": [{"Name": n, "Value": values[n]} for n in Names if n in values],
            "InvalidParameters": [n for n in Names if n not in values],
        }

    ssm = MagicMock()
    ssm.get_parameters.side_effect = get_parameters
    return ssm


def test_secrets_are_loaded_into_the_environment_with_decryption():
    names = {f"/finrag/{p}": f"value-{p}" for p in SECRET_PARAMETERS}
    ssm = _ssm_returning(names)

    with patch.dict("os.environ", {}, clear=True):
        import os

        load_secrets_from_ssm(ssm, prefix="/finrag")
        for param, env_var in SECRET_PARAMETERS.items():
            assert os.environ[env_var] == f"value-{param}"

    kwargs = ssm.get_parameters.call_args.kwargs
    assert kwargs["WithDecryption"] is True


def test_values_already_in_the_environment_are_not_overwritten():
    """Local dev and the eval harness set keys directly; SSM must not clobber them."""
    ssm = _ssm_returning({f"/finrag/{p}": "from-ssm" for p in SECRET_PARAMETERS})
    env_var = next(iter(SECRET_PARAMETERS.values()))

    with patch.dict("os.environ", {env_var: "from-env"}, clear=True):
        import os

        load_secrets_from_ssm(ssm, prefix="/finrag")
        assert os.environ[env_var] == "from-env"


def test_missing_parameter_fails_loudly():
    """A missing key must stop the cold start, not surface later as a vague
    auth error on the first OpenAI or Pinecone call."""
    import pytest

    ssm = MagicMock()
    ssm.get_parameters.return_value = {
        "Parameters": [],
        "InvalidParameters": [f"/finrag/{p}" for p in SECRET_PARAMETERS],
    }
    with patch.dict("os.environ", {}, clear=True), pytest.raises(RuntimeError, match="missing"):
        load_secrets_from_ssm(ssm, prefix="/finrag")

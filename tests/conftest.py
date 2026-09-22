"""Shared test setup: dummy env vars so importing server.main never needs
real credentials or a real Pinecone account during unit tests."""
import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault("PINECONE_API_KEY", "test-key-for-unit-tests")

# ragas 0.4.x pulls in arize-phoenix which has a broken openinference import
# on Python 3.13. Stub the broken sub-modules before pytest collects any file.
for _mod in (
    "openinference.instrumentation",
    "phoenix.client",
    "phoenix.client.client",
    "phoenix.client.resources",
    "phoenix.client.resources.experiments",
    "langchain_community.chat_models.vertexai",
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

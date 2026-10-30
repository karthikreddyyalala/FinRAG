"""Shared pytest fixtures for tests/unit/.

Unit tests must never depend on a real network call or a real ML model
download -- that is an infra/network concern, not application logic under
test, and it makes CI non-deterministic (slow cold download, or genuinely
different behavior on whichever platform/architecture the runner happens
to be). rerank() calls Voyage's
hosted API whenever VOYAGE_API_KEY is set, which it is on any machine that
has run the eval harness. This fixture clears it for the whole suite so every
test gets the deterministic lexical scorer unless it sets a key itself (see
test_reranker_voyage.py, which mocks the HTTP call).
"""
import pytest


@pytest.fixture(autouse=True)
def _force_lexical_reranker(monkeypatch):
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)

"""Shared pytest fixtures for tests/unit/.

Unit tests must never depend on a real network call or a real ML model
download -- that is an infra/network concern, not application logic under
test, and it makes CI non-deterministic (slow cold download, or genuinely
different behavior on whichever platform/architecture the runner happens
to be). reranker.py's real CrossEncoder path is gated off on the macOS +
Python 3.13 dev machine this project was built on (torch deadlocks there),
but that gate does NOT engage on CI (Ubuntu + Python 3.12) or on most
other machines -- so without this fixture, a test run on any other
platform silently exercises a real, network-dependent ML model instead of
this project's own retrieval code, and got exactly that: CI's
"Unit tests" step kept failing even after two files were fixed to force
the lexical path individually, because the platform-gate approach is
inherently whack-a-mole -- any test that calls rerank() without local
mocking is exposed, not just the ones already found. This fixture forces
the deterministic lexical fallback for the entire test suite, globally,
so no individual test file needs to remember to do this itself.
"""
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _force_lexical_reranker():
    with patch("server.retrieval.reranker._crossencoder_available", return_value=False):
        yield

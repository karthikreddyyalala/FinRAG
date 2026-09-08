"""Shared test setup: dummy env vars so importing server.main never needs
real credentials or a real Pinecone account during unit tests."""
import os

os.environ.setdefault("PINECONE_API_KEY", "test-key-for-unit-tests")

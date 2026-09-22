"""TDD: loading the BM25 index from S3 must survive a mid-download timeout.

load_bm25_index reads a 974MB pickle in a single s3_client.get_object(...)
.read() call with no retry. A ReadTimeoutError mid-stream killed an eval run
before a single question was processed -- the whole 974MB download had to
restart from zero on the next attempt. Every other network-facing call in
this codebase (EDGAR, Bedrock, OpenAI) already retries transient faults by
exception type; this was the one still missing it.
"""
import pickle
from unittest.mock import MagicMock

import botocore.exceptions
import pytest

from pipeline.sync_pinecone import load_bm25_index


def _payload_body(chunks):
    blob = pickle.dumps({"bm25": "fake-bm25-object", "chunks": chunks})
    body = MagicMock()
    body.read.return_value = blob
    return body


def test_read_timeout_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    chunks = [{"chunk_id": "c1", "text": "x"}]
    calls = {"n": 0}

    def get_object(**kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise botocore.exceptions.ReadTimeoutError(endpoint_url="https://s3/x")
        return {"Body": _payload_body(chunks)}

    s3 = MagicMock()
    s3.get_object.side_effect = get_object

    bm25, loaded = load_bm25_index(s3, "bucket", "key")

    assert bm25 == "fake-bm25-object"
    assert loaded == chunks
    assert calls["n"] == 3


def test_persistent_timeout_eventually_raises(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)

    s3 = MagicMock()
    s3.get_object.side_effect = botocore.exceptions.ReadTimeoutError(endpoint_url="https://s3/x")

    with pytest.raises(botocore.exceptions.ReadTimeoutError):
        load_bm25_index(s3, "bucket", "key")


def test_non_timeout_errors_are_not_retried(monkeypatch):
    """A real error (e.g. missing key) must not be masked by blind retrying."""
    monkeypatch.setattr("time.sleep", lambda *_: None)
    calls = {"n": 0}

    def get_object(**kwargs):
        calls["n"] += 1
        raise s3.exceptions.NoSuchKey({"Error": {}}, "GetObject")

    s3 = MagicMock()
    s3.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
    s3.get_object.side_effect = get_object

    with pytest.raises(s3.exceptions.NoSuchKey):
        load_bm25_index(s3, "bucket", "key")
    assert calls["n"] == 1, "a real error was retried instead of raised immediately"

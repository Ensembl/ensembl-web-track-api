"""Isolate Redis state for every test without requiring a running server."""

from unittest.mock import Mock

import pytest

from utils import redis_cache


@pytest.fixture(autouse=True)
def isolated_redis(monkeypatch):
    monkeypatch.setattr(redis_cache, "_database_version", None)
    monkeypatch.setattr(redis_cache, "_version_initialized", False)
    entries = {}
    client = Mock()
    client.get.side_effect = entries.get

    def setex(key, ttl, value):
        entries[key] = value
        return True

    client.setex.side_effect = setex
    client.flushdb.side_effect = entries.clear
    monkeypatch.setattr(redis_cache, "redis_client", client)
    client.flushdb()
    yield client
    client.flushdb()

"""redis_cache.py against fakeredis."""

import os
from types import SimpleNamespace

import fakeredis
import pytest

import redis_cache
from assistant.assistant_model import AssistantSubject, Operation, Operations
from redis_cache import RedisCache


@pytest.fixture
def server(monkeypatch):
    server = fakeredis.FakeServer()
    urls = []

    def from_url(url, **kwargs):
        urls.append(url)
        return fakeredis.FakeRedis(server=server)

    monkeypatch.setattr(redis_cache.redis.Redis, "from_url", from_url)
    # redis-om's migrations would connect to the real REDIS_OM_URL
    monkeypatch.setattr(redis_cache, "Migrator", lambda: SimpleNamespace(run=lambda: None))
    monkeypatch.delenv("REDIS_OM_URL", raising=False)
    server.urls = urls
    return server


def ops(label="ship"):
    return Operations(operations=[Operation(operation="add", data=AssistantSubject(uri="u", label=label, id="s"))])


def test_connects_to_url(server):
    RedisCache(redis_url="redis://cache:6379/3", model=Operations)
    assert server.urls == ["redis://cache:6379/3"]
    assert os.environ["REDIS_OM_URL"] == "redis://cache:6379/3"


def test_get_set(server):
    cache = RedisCache(model=Operations)
    assert cache.get("missing") is None and cache["missing"] is None
    cache["k"] = ops()
    assert cache["k"] == ops()
    assert isinstance(cache.get("k"), Operations)
    cache.set("short", ops(), ttl=10)
    assert 0 < cache.redis.ttl("short") <= 10
    assert 0 < cache.redis.ttl("k") <= 24 * 60 * 60


def test_get_or_set_computes_once(server):
    cache = RedisCache(model=Operations)
    calls = []

    def compute():
        calls.append(1)
        return ops("computed")

    assert cache.get_or_set("key", compute) == ops("computed")
    assert cache.get_or_set("key", compute) == ops("computed")
    assert len(calls) == 1
    # a second cache on the same server sees the entry
    assert RedisCache(model=Operations).get_or_set("key", compute) == ops("computed")
    assert len(calls) == 1

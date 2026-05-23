"""Coverage for app.core.cache graceful Redis degradation."""

from __future__ import annotations

import pytest

from app.core import cache as cache_module


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.fail_get = False
        self.fail_set = False

    def ping(self) -> bool:
        return True

    def get(self, key: str):
        if self.fail_get:
            raise RuntimeError("get explosion")
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        if self.fail_set:
            raise RuntimeError("set explosion")
        self.store[key] = value


@pytest.fixture(autouse=True)
def _reset_cache_singleton():
    cache_module._redis = None
    cache_module._redis_checked = False
    yield
    cache_module._redis = None
    cache_module._redis_checked = False


def test_cache_get_returns_none_when_redis_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache_module, "_connect_redis", lambda: None)
    assert cache_module.cache_get("any-key") is None


def test_cache_set_is_silent_when_redis_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache_module, "_connect_redis", lambda: None)
    # Must not raise even though Redis is unreachable.
    cache_module.cache_set("k", {"value": 1}, ttl_seconds=10)


def test_cache_roundtrip_with_fake_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(cache_module, "_connect_redis", lambda: fake)
    cache_module.cache_set("foo", {"a": 1, "ru": "Москва"}, ttl_seconds=60)
    assert cache_module.cache_get("foo") == {"a": 1, "ru": "Москва"}


def test_cache_get_missing_key_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(cache_module, "_connect_redis", lambda: fake)
    assert cache_module.cache_get("missing") is None


def test_cache_get_swallows_runtime_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedis()
    fake.fail_get = True
    monkeypatch.setattr(cache_module, "_connect_redis", lambda: fake)
    assert cache_module.cache_get("foo") is None


def test_cache_set_swallows_runtime_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedis()
    fake.fail_set = True
    monkeypatch.setattr(cache_module, "_connect_redis", lambda: fake)
    cache_module.cache_set("foo", {"a": 1})  # must not raise
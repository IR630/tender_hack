"""Redis cache with graceful degradation when Redis is down."""

from __future__ import annotations

import json
import logging
from typing import Any

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None
_redis_checked = False


def _connect_redis() -> redis.Redis | None:
    try:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception as exc:
        logger.warning("Redis unavailable (%s); cache disabled", exc)
        return None


def get_redis() -> redis.Redis | None:
    global _redis, _redis_checked
    if _redis is not None:
        try:
            _redis.ping()
            return _redis
        except Exception:
            _redis = None
    if not _redis_checked:
        _redis_checked = True
    _redis = _connect_redis()
    return _redis


def cache_get(key: str) -> Any | None:
    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(key)
    except Exception as exc:
        logger.warning("Redis GET failed for %r: %s", key, exc)
        return None
    if raw is None:
        return None
    return json.loads(raw)


def cache_set(key: str, value: Any, ttl_seconds: int | None = None) -> None:
    client = get_redis()
    if client is None:
        return
    ttl = ttl_seconds if ttl_seconds is not None else settings.cache_ttl_seconds
    try:
        client.setex(key, ttl, json.dumps(value, ensure_ascii=False))
    except Exception as exc:
        logger.warning("Redis SET failed for %r: %s", key, exc)

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from ozon_public_scraper.config import settings
from ozon_public_scraper.logging_config import get_logger

logger = get_logger("ozon_public.storage.cache")

_client: aioredis.Redis | None = None


async def get_client() -> aioredis.Redis | None:
    global _client
    if _client is not None:
        return _client
    try:
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await _client.ping()
        return _client
    except Exception as exc:
        logger.warning("redis_unavailable", context={"error": str(exc)})
        return None


async def cache_get(key: str) -> Any | None:
    client = await get_client()
    if client is None:
        return None
    try:
        raw = await client.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("cache_get_failed", context={"key": key, "error": str(exc)})
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    client = await get_client()
    if client is None:
        return
    try:
        await client.setex(key, ttl_seconds, json.dumps(value, ensure_ascii=False))
    except Exception as exc:
        logger.warning("cache_set_failed", context={"key": key, "error": str(exc)})


def searxng_cache_key(query: str) -> str:
    return f"searxng:{query.strip().lower()}"


def og_cache_key(numeric_id: str) -> str:
    return f"og:{numeric_id}"


def blocked_url_key(numeric_id: str) -> str:
    return f"ozon_blocked:{numeric_id}"

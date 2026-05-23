"""Disk-backed cache for Ozon nodriver search results."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from diskcache import Cache

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "data" / "ozon_disk_cache"
DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24 hours

_cache: Cache | None = None


def _get_cache() -> Cache:
    global _cache
    if _cache is None:
        cache_dir = Path(os.getenv("OZON_DISK_CACHE_DIR", str(DEFAULT_CACHE_DIR)))
        cache_dir.mkdir(parents=True, exist_ok=True)
        _cache = Cache(str(cache_dir))
    return _cache


def _normalize_key(query: str) -> str:
    return query.strip().lower()


def get_cached_products(query: str) -> list[dict[str, Any]] | None:
    """Return cached product list or None on miss."""
    key = _normalize_key(query)
    raw = _get_cache().get(key)
    if raw is None:
        return None
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def set_cached_products(query: str, products: list[dict[str, Any]], *, ttl: int = DEFAULT_TTL_SECONDS) -> None:
    key = _normalize_key(query)
    _get_cache().set(key, json.dumps(products, ensure_ascii=False), expire=ttl)


def clear_cache() -> None:
    _get_cache().clear()


def cache_stats() -> dict[str, int]:
    c = _get_cache()
    return {"size": len(c), "volume": c.volume()}

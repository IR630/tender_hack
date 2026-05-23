import json
from pathlib import Path

import pytest

from cache_manager import get_cached_products, set_cached_products


@pytest.fixture()
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import cache_manager as cm

    monkeypatch.setenv("OZON_DISK_CACHE_DIR", str(tmp_path / "cache"))
    cm._cache = None
    yield tmp_path
    if cm._cache is not None:
        cm._cache.clear()
        cm._cache.close()
        cm._cache = None


def test_cache_miss_then_hit(isolated_cache: Path) -> None:
    assert get_cached_products("принтер hp") is None
    products = [{"title": "HP", "price": 10000, "url": "https://ozon.ru/p/1", "image": None}]
    set_cached_products("принтер hp", products, ttl=3600)
    cached = get_cached_products("принтер HP")
    assert cached is not None
    assert len(cached) == 1
    assert cached[0]["title"] == "HP"


def test_cache_key_normalization(isolated_cache: Path) -> None:
    set_cached_products("  Ноутбук  ", [{"title": "X", "price": 1, "url": "u", "image": None}])
    assert get_cached_products("ноутбук") is not None

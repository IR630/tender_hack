"""Unit tests for Wildberries scraper (no network: HTTP layer is mocked)."""

import importlib
import sys

import pytest

from app.core.models import Product, SearchRequest
from app.scrapers import wb
from app.scrapers.wb.models import WBSearchResponse

wb_scraper_module = sys.modules.get("app.scrapers.wb.scraper") or importlib.import_module(
    "app.scrapers.wb.scraper"
)


@pytest.fixture(autouse=True)
async def _reset_wb_state():
    await wb.reset_session_for_tests()
    yield
    await wb.reset_session_for_tests()


def _search_payload() -> dict:
    return {
        "products": [
            {
                "id": 179040120,
                "name": "Шины зимние 205 55 R16",
                "brand": "iLINK",
                "supplier": "Мосавтошина",
                "reviewRating": 4.9,
                "nmFeedbacks": 22912,
                "sizes": [{"price": {"basic": 5000000, "product": 4073000}}],
            },
            {
                "id": 200000001,
                "name": "Без характеристик",
                "sizes": [{"price": {"product": 1500000}}],
            },
            {
                "id": 200000002,
                "name": "Нет цены",
                "sizes": [{"price": {"product": 0}}],
            },
        ]
    }


async def test_search_maps_fields_from_search_api(monkeypatch):
    async def fake_fetch(params):
        return WBSearchResponse(_search_payload()["products"], status_code=200)

    monkeypatch.setattr(wb.wb_session, "fetch_search", fake_fetch)

    async def no_cache(region, query):
        return None

    async def no_store(region, query, products):
        return None

    monkeypatch.setattr(wb_scraper_module, "_load_cached_products", no_cache)
    monkeypatch.setattr(wb_scraper_module, "_store_cached_products", no_store)

    products = await wb.scraper.search(SearchRequest(query="шины"))

    assert len(products) == 2
    first = products[0]
    assert first.source == "wildberries"
    assert first.price == 4_073_000
    assert first.product_url == "https://www.wildberries.ru/catalog/179040120/detail.aspx"
    assert "basket-" in first.image_url
    assert first.rating == 4.9
    assert first.reviews_count == 22912
    assert first.characteristics["Бренд"] == "iLINK"
    assert first.characteristics["Продавец"] == "Мосавтошина"
    assert "Характеристики:" in first.description
    assert "• Бренд: iLINK" in first.description
    assert "Рейтинг: 4.9" in first.description
    assert "22912 отзывов" in first.description
    assert wb.scraper.last_error is None


async def test_search_surfaces_429_error(monkeypatch):
    async def fake_fetch(params):
        return WBSearchResponse(
            [],
            status_code=429,
            error="HTTP 429: антибот Wildberries (rate-limit или IP). "
            "Подождите или используйте российский IP без VPN.",
        )

    monkeypatch.setattr(wb.wb_session, "fetch_search", fake_fetch)

    async def no_cache(region, query):
        return None

    monkeypatch.setattr(wb_scraper_module, "_load_cached_products", no_cache)

    products = await wb.scraper.search(SearchRequest(query="ноутбук"))
    assert products == []
    assert wb.scraper.last_error is not None
    assert "429" in wb.scraper.last_error


async def test_search_uses_cache_without_fetch(monkeypatch):
    cached = [
        {
            "source": "wildberries",
            "source_domain": "wildberries.ru",
            "title": "Кешированный товар",
            "description": "",
            "price": 10000,
            "currency": "RUB",
            "image_url": "https://example.com/a.webp",
            "product_url": "https://www.wildberries.ru/catalog/1/detail.aspx",
            "characteristics": {},
            "rating": None,
            "reviews_count": None,
            "relevance_score": 0.0,
            "confidence": 1.0,
        }
    ]

    async def fake_load(region, query):
        return [Product.model_validate(item) for item in cached]

    called = {"fetch": False}

    async def fake_fetch(params):
        called["fetch"] = True
        return WBSearchResponse([], status_code=200)

    monkeypatch.setattr(wb_scraper_module, "_load_cached_products", fake_load)
    monkeypatch.setattr(wb.wb_session, "fetch_search", fake_fetch)

    products = await wb.scraper.search(SearchRequest(query="шины"))
    assert len(products) == 1
    assert products[0].title == "Кешированный товар"
    assert called["fetch"] is False


async def test_circuit_breaker_blocks_after_trip(monkeypatch):
    from app.scrapers.wb.circuit import trip_circuit

    trip_circuit()
    trip_circuit()
    trip_circuit()

    async def no_cache(region, query):
        return None

    monkeypatch.setattr(wb_scraper_module, "_load_cached_products", no_cache)

    products = await wb.scraper.search(SearchRequest(query="шины"))
    assert products == []
    assert wb.scraper.last_error is not None
    err = wb.scraper.last_error.lower()
    assert "circuit" in err or "недоступен" in err


def test_price_kopecks_variants():
    assert wb.price_kopecks({"sizes": [{"price": {"product": 4073000}}]}) == 4073000
    assert wb.price_kopecks({"sizes": [{"price": {"basic": 5000000}}]}) == 5000000
    assert wb.price_kopecks({"salePriceU": 199900}) == 199900
    assert wb.price_kopecks({"sizes": []}) == 0


def test_image_url_uses_host_hint():
    nm = 179040120
    host = wb.host_for_nm(nm)
    url = wb.image_url(host, nm)
    assert url.startswith(f"https://basket-{host:02d}.wbbasket.ru/")


def test_build_description_from_search_fields():
    chars = wb.extended_characteristics(
        {
            "brand": "Nike",
            "supplier": "SportShop",
            "entity": "кроссовки",
            "colors": ["черный", "белый"],
        }
    )
    desc = wb.build_description(characteristics=chars, rating=4.8, reviews_count=120)
    assert "• Бренд: Nike" in desc
    assert "• Цвет: черный, белый" in desc
    assert "Рейтинг: 4.8 (120 отзывов)" in desc


def test_parse_search_products_rejects_throttled_single_item():
    from app.scrapers.wb.session import _parse_search_products

    legacy = _parse_search_products({"products": [{"id": i} for i in range(6)]})
    assert len(legacy) == 6

    throttled = _parse_search_products(
        {"data": {"products": [{"id": 99, "name": "Платье"}]}}
    )
    assert throttled == []

    nested = _parse_search_products(
        {"data": {"products": [{"id": i} for i in range(8)]}}
    )
    assert len(nested) == 8

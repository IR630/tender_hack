import pytest

from app.core.models import SearchRequest
from app.scrapers import ozon
from parser_ozon import ParsedProduct, SearchResult


@pytest.mark.asyncio
async def test_ozon_marks_cached_results_from_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cached_product = ParsedProduct(
        title="Футболка мужская хлопок базовая",
        price=1299,
        image_url="https://cdn.example.test/tshirt.jpg",
        product_url="https://www.ozon.ru/product/futbolka-123/",
        characteristics={"Материал": "Хлопок"},
        confidence=0.85,
    )

    async def fake_search(query: str) -> SearchResult:
        return SearchResult(
            query=query,
            status="cached",
            method_used="demo_cache",
            products=[cached_product],
            cached_at="2026-05-22T22:00:00Z",
            is_cached=True,
        )

    monkeypatch.setattr(ozon._parser, "search", fake_search)

    products, meta = await ozon.scraper.search_with_meta(SearchRequest(query="футболка мужская"))

    assert len(products) == 1
    assert products[0].title == "Футболка мужская хлопок базовая"
    assert meta["status"] == "cached"
    assert meta["cache_timestamp"] == "2026-05-22T22:00:00Z"
    assert "кэшированные данные" in (meta["notice"] or "").lower()


@pytest.mark.asyncio
async def test_ozon_reports_temporary_unavailability_without_products(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search(query: str) -> SearchResult:
        return SearchResult(
            query=query,
            status="blocked",
            method_used=None,
            blocked_reason="http_403",
        )

    monkeypatch.setattr(ozon._parser, "search", fake_search)

    products, meta = await ozon.scraper.search_with_meta(SearchRequest(query="iphone 15"))

    assert products == []
    assert meta["status"] == "temporarily_unavailable"
    assert "временно недоступен" in (meta["notice"] or "").lower()

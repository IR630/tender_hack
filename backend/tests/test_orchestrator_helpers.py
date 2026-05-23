"""Pure-helper coverage for app.orchestrator.search."""

from __future__ import annotations

import pytest

from app.core.models import Product, SearchGroup
from app.orchestrator import search as orch
from app.orchestrator.search import (
    SOURCE_ORDER,
    _active_source_order,
    _build_group,
    _build_summary,
    _enabled_sources,
    _safe_search,
)


def _make_product(source: str, price: int) -> Product:
    return Product(
        source=source,  # type: ignore[arg-type]
        source_domain=f"{source}.example",
        title=f"item-{price}",
        price=price,
        image_url="https://example.com/i.jpg",
        product_url=f"https://example.com/p/{price}",
    )


def test_enabled_sources_star_returns_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orch.settings, "search_enabled_sources", "*")
    assert _enabled_sources() == frozenset(SOURCE_ORDER)


def test_enabled_sources_empty_returns_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orch.settings, "search_enabled_sources", "")
    assert _enabled_sources() == frozenset(SOURCE_ORDER)


def test_enabled_sources_subset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orch.settings, "search_enabled_sources", "wildberries, other ,")
    assert _enabled_sources() == frozenset({"wildberries", "other"})


def test_active_source_order_preserves_canonical_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orch.settings, "search_enabled_sources", "ozon,wildberries,other")
    # Canonical SOURCE_ORDER is wildberries, yandex_market, other, ozon
    assert _active_source_order() == ("wildberries", "other", "ozon")


def test_build_summary_empty_returns_zero_summary() -> None:
    summary = _build_summary([])
    assert summary.total_found == 0
    assert summary.min_price is None
    assert summary.median_price is None
    assert summary.max_price is None


def test_build_summary_ignores_zero_priced_products() -> None:
    group = SearchGroup(
        source="wildberries",
        display_name="WB",
        products=[_make_product("wildberries", 0), _make_product("wildberries", 1000)],
    )
    summary = _build_summary([group])
    assert summary.total_found == 1
    assert summary.min_price == 1000
    assert summary.max_price == 1000


def test_build_summary_median_for_even_count() -> None:
    group = SearchGroup(
        source="wildberries",
        display_name="WB",
        products=[_make_product("wildberries", p) for p in (100, 200, 300, 400)],
    )
    summary = _build_summary([group])
    assert summary.total_found == 4
    assert summary.min_price == 100
    assert summary.max_price == 400
    # median = (200 + 300) // 2 = 250
    assert summary.median_price == 250


def test_build_summary_median_for_odd_count() -> None:
    group = SearchGroup(
        source="wildberries",
        display_name="WB",
        products=[_make_product("wildberries", p) for p in (100, 500, 900)],
    )
    summary = _build_summary([group])
    assert summary.median_price == 500


def test_build_group_dedupes_and_sorts_domains() -> None:
    products = [
        Product(
            source="other",
            source_domain="dns.ru",
            title="t",
            price=10,
            image_url="",
            product_url="https://dns.ru/1",
        ),
        Product(
            source="other",
            source_domain="citilink.ru",
            title="t",
            price=20,
            image_url="",
            product_url="https://citilink.ru/2",
        ),
        Product(
            source="other",
            source_domain="dns.ru",
            title="t",
            price=30,
            image_url="",
            product_url="https://dns.ru/3",
        ),
    ]
    group = _build_group("other", products, error=None, status=None)
    assert group.count == 3
    assert group.min_price == 10
    assert group.domains == ["citilink.ru", "dns.ru"]
    assert group.error is None


def test_build_group_empty_min_price_none() -> None:
    group = _build_group("other", [], error="boom", status="x")
    assert group.count == 0
    assert group.min_price is None
    assert group.error == "boom"
    assert group.status == "x"


@pytest.mark.asyncio
async def test_safe_search_returns_products_and_error_from_scraper() -> None:
    class FakeScraper:
        source = "wildberries"
        last_error = "rate-limited"
        last_source_status = "blocked"

        def clear_error(self) -> None:
            self.last_error = "rate-limited"  # left unchanged on purpose

    async def coro() -> list[Product]:
        return [_make_product("wildberries", 42)]

    products, error, status = await _safe_search(FakeScraper(), coro())
    assert len(products) == 1
    assert error == "rate-limited"
    assert status == "blocked"


@pytest.mark.asyncio
async def test_safe_search_catches_exception() -> None:
    class FakeScraper:
        source = "ozon"

    async def coro() -> list[Product]:
        raise RuntimeError("WAF tripped")

    products, error, status = await _safe_search(FakeScraper(), coro())
    assert products == []
    assert error is not None and "RuntimeError" in error and "WAF tripped" in error
    assert status is None


@pytest.mark.asyncio
async def test_safe_search_tolerates_none_scraper() -> None:
    async def coro() -> list[Product]:
        return []

    products, error, status = await _safe_search(None, coro())
    assert products == []
    assert error is None
    assert status is None

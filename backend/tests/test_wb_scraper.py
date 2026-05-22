"""Unit tests for the Wildberries scraper (no network: httpx is mocked)."""

import httpx
import pytest

from app.core.models import SearchRequest
from app.scrapers import wb


@pytest.fixture(autouse=True)
def _clear_basket_memo():
    wb._basket_memo.clear()
    yield
    wb._basket_memo.clear()


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
            {  # dropped: no price
                "id": 200000002,
                "name": "Нет цены",
                "sizes": [{"price": {"product": 0}}],
            },
        ]
    }


def _card_payload() -> dict:
    return {
        "subj_name": "Шины автомобильные",
        "options": [{"name": "Ширина, мм", "value": "205"}],
        "grouped_options": [{"options": [{"name": "Сезон", "value": "зима"}]}],
    }


def _make_client(handler) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport, headers=wb.BROWSER_HEADERS)


async def test_search_maps_fields_and_enriches(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "search.wb.ru" in url:
            return httpx.Response(200, json=_search_payload())
        if url.endswith("/images/big/1.webp"):
            # only basket-12 "exists" for these volumes
            return httpx.Response(200 if "basket-12" in url else 404)
        if url.endswith("card.json"):
            return httpx.Response(200, json=_card_payload())
        return httpx.Response(404)

    client = _make_client(handler)
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: client)

    products = await wb.scraper.search(SearchRequest(query="шины"))

    assert len(products) == 2  # zero-price item dropped
    first = products[0]
    assert first.source == "wildberries"
    assert first.source_domain == "wildberries.ru"
    assert first.price == 40730  # 4073000 kopecks / 100
    assert first.product_url == "https://www.wildberries.ru/catalog/179040120/detail.aspx"
    assert "basket-12" in first.image_url
    assert first.rating == 4.9
    assert first.reviews_count == 22912
    # enriched from card.json + base brand/supplier
    assert first.characteristics["Категория"] == "Шины автомобильные"
    assert first.characteristics["Ширина, мм"] == "205"
    assert first.characteristics["Сезон"] == "зима"
    assert first.characteristics["Бренд"] == "iLINK"


async def test_search_returns_empty_on_429(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Too Many Requests")

    client = _make_client(handler)
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: client)

    products = await wb.scraper.search(SearchRequest(query="ноутбук"))
    assert products == []


async def test_missing_basket_host_yields_empty_image(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "search.wb.ru" in url:
            return httpx.Response(200, json=_search_payload())
        return httpx.Response(404)  # no basket host serves the image

    client = _make_client(handler)
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: client)

    products = await wb.scraper.search(SearchRequest(query="шины"))
    assert products  # still returned, just without an image
    assert all(p.image_url == "" for p in products)


def test_price_rub_variants():
    assert wb._price_rub({"sizes": [{"price": {"product": 4073000}}]}) == 40730
    assert wb._price_rub({"sizes": [{"price": {"basic": 5000000}}]}) == 50000
    assert wb._price_rub({"salePriceU": 199900}) == 1999
    assert wb._price_rub({"sizes": []}) == 0

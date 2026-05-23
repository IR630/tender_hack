"""Unit tests for the Wildberries scraper (no network: HTTP layer is mocked)."""

import pytest

from app.core.models import Product, SearchRequest
from app.scrapers import wb


@pytest.fixture(autouse=True)
def _reset_wb_state():
    wb.reset_session_for_tests()
    yield
    wb.reset_session_for_tests()


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


async def test_search_maps_fields_from_search_api(monkeypatch):
    monkeypatch.setattr(
        wb,
        "_fetch_search_sync",
        lambda params: wb._SearchResponse(_search_payload()["products"], status_code=200),
    )

    async def no_cache(region, query):
        return None

    async def no_store(region, query, products):
        return None

    monkeypatch.setattr(wb, "_load_cached_products", no_cache)
    monkeypatch.setattr(wb, "_store_cached_products", no_store)

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
    assert wb.scraper.last_error is None


def test_fetch_search_retries_after_429(monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
            self.status_code = status_code
            self.text = text
            self.headers = {}

        def json(self) -> dict:
            return {"products": _search_payload()["products"]}

    class FakeSession:
        def get(self, *args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return FakeResponse(429, text="blocked")
            return FakeResponse(200)

    monkeypatch.setattr(wb, "_get_session", lambda: FakeSession())
    monkeypatch.setattr(wb, "_reset_session", lambda: None)
    monkeypatch.setattr(wb, "_trip_circuit", lambda: None)
    monkeypatch.setattr(wb.time, "sleep", lambda _: None)

    result = wb._fetch_search_sync({"query": "шины"})
    assert calls["count"] == 2
    assert len(result.products) == 3
    assert result.error is None


async def test_search_surfaces_429_error(monkeypatch):
    monkeypatch.setattr(
        wb,
        "_fetch_search_sync",
        lambda params: wb._SearchResponse(
            [],
            status_code=429,
            error="HTTP 429: антибот Wildberries (rate-limit или IP). "
            "Подождите или используйте российский IP без VPN.",
        ),
    )

    async def no_cache(region, query):
        return None

    monkeypatch.setattr(wb, "_load_cached_products", no_cache)

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

    def fake_fetch(params):
        called["fetch"] = True
        return wb._SearchResponse([], status_code=200)

    monkeypatch.setattr(wb, "_load_cached_products", fake_load)
    monkeypatch.setattr(wb, "_fetch_search_sync", fake_fetch)

    products = await wb.scraper.search(SearchRequest(query="шины"))
    assert len(products) == 1
    assert products[0].title == "Кешированный товар"
    assert called["fetch"] is False


async def test_circuit_breaker_blocks_after_trip(monkeypatch):
    wb._trip_circuit()

    async def no_cache(region, query):
        return None

    monkeypatch.setattr(wb, "_load_cached_products", no_cache)

    products = await wb.scraper.search(SearchRequest(query="шины"))
    assert products == []
    assert wb.scraper.last_error is not None
    assert "circuit" in wb.scraper.last_error.lower() or "недоступен" in wb.scraper.last_error.lower()


def test_price_kopecks_variants():
    assert wb._price_kopecks({"sizes": [{"price": {"product": 4073000}}]}) == 4073000
    assert wb._price_kopecks({"sizes": [{"price": {"basic": 5000000}}]}) == 5000000
    assert wb._price_kopecks({"salePriceU": 199900}) == 199900
    assert wb._price_kopecks({"sizes": []}) == 0


def test_image_url_uses_host_hint():
    nm = 179040120
    host = wb._host_for_nm(nm)
    url = wb._image_url(host, nm)
    assert url.startswith(f"https://basket-{host:02d}.wbbasket.ru/")


def test_session_uses_configured_impersonate(monkeypatch):
    captured = {}

    class FakeSession:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(wb.curl_requests, "Session", FakeSession)
    wb._reset_session()
    wb._get_session()
    assert captured.get("impersonate") == wb.settings.wb_impersonate


def test_browser_headers_have_no_hardcoded_user_agent():
    # curl_cffi owns the UA so it stays consistent with the impersonated TLS fingerprint.
    assert "user-agent" not in {key.lower() for key in wb.BROWSER_HEADERS}


def test_retry_after_header_respected(monkeypatch):
    responses = [(429, {"Retry-After": "2"}), (200, {})]
    calls = {"i": 0}

    class FakeResponse:
        def __init__(self, status_code: int, headers: dict):
            self.status_code = status_code
            self.headers = headers
            self.text = ""

        def json(self) -> dict:
            return {"products": _search_payload()["products"]}

    class FakeSession:
        def get(self, *args, **kwargs):
            status, headers = responses[calls["i"]]
            calls["i"] += 1
            return FakeResponse(status, headers)

    slept: list[float] = []
    monkeypatch.setattr(wb, "_get_session", lambda: FakeSession())
    monkeypatch.setattr(wb, "_reset_session", lambda: None)
    monkeypatch.setattr(wb, "_trip_circuit", lambda: None)
    monkeypatch.setattr(wb.time, "sleep", lambda s: slept.append(s))

    result = wb._fetch_search_sync({"query": "шины"})

    assert result.error is None
    assert len(result.products) == 3
    assert len(slept) == 1
    # Retry-After=2s honored, plus jitter up to 25%, capped at wb_retry_max_backoff_seconds.
    assert 2.0 <= slept[0] <= 2.5


def test_backoff_grows_and_trips_circuit(monkeypatch):
    class FakeResponse:
        status_code = 429
        text = "blocked"
        headers: dict = {}

    calls = {"count": 0}

    class FakeSession:
        def get(self, *args, **kwargs):
            calls["count"] += 1
            return FakeResponse()

    slept: list[float] = []
    tripped = {"v": False}
    monkeypatch.setattr(wb, "_get_session", lambda: FakeSession())
    monkeypatch.setattr(wb, "_reset_session", lambda: None)
    monkeypatch.setattr(wb, "_trip_circuit", lambda: tripped.__setitem__("v", True))
    monkeypatch.setattr(wb.time, "sleep", lambda s: slept.append(s))

    result = wb._fetch_search_sync({"query": "шины"})

    assert calls["count"] == wb.settings.wb_retry_max_attempts
    assert len(slept) == wb.settings.wb_retry_max_attempts - 1
    if len(slept) >= 2:
        assert slept[1] > slept[0]  # exponential growth between attempts
    assert tripped["v"] is True
    assert result.products == []
    assert "429" in (result.error or "")

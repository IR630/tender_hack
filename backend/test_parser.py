import json

import pytest

from parser_ozon import MethodAttempt, OzonParser, ParsedProduct


@pytest.mark.asyncio
async def test_search_returns_mobile_html_products(monkeypatch: pytest.MonkeyPatch) -> None:
    parser = OzonParser(results_dir="results/test_parser_html")

    async def fake_mobile_html(query: str) -> MethodAttempt:
        return MethodAttempt(
            method="mobile_html",
            status="success",
            latency_ms=12,
            products_found=1,
            fields_completeness={
                "title": 1,
                "price": 1,
                "image": 1,
                "url": 1,
                "characteristics": 1,
            },
            products=[
                ParsedProduct(
                    title="Футболка мужская хлопок",
                    price=1299,
                    image_url="https://cdn.example.test/tshirt.jpg",
                    product_url="https://www.ozon.ru/product/demo-1/",
                    characteristics={"Материал": "Хлопок"},
                    confidence=0.8,
                )
            ],
            http_status=200,
        )

    async def fake_mobile_browser(query: str) -> MethodAttempt:
        return MethodAttempt(
            method="mobile_browser",
            status="failed",
            latency_ms=0,
            products_found=0,
            fields_completeness={
                "title": 0,
                "price": 0,
                "image": 0,
                "url": 0,
                "characteristics": 0,
            },
        )

    monkeypatch.setattr(parser, "_search_mobile_html", fake_mobile_html)
    monkeypatch.setattr(parser, "_search_mobile_browser", fake_mobile_browser)

    result = await parser.search("футболка мужская хлопок", use_cache=False)

    assert result.method_used == "mobile_html"
    assert result.status == "success"
    assert result.is_cached is False
    assert len(result.products) == 1


@pytest.mark.asyncio
async def test_search_falls_back_to_demo_cache(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    demo_cache_path = tmp_path / "ozon_demo_cache.json"
    demo_cache_path.write_text(
        json.dumps(
            {
                "cached_at": "2026-05-22T22:00:00Z",
                "products": [
                    {
                        "title": "Футболка мужская хлопок базовая",
                        "price": 1299,
                        "image_url": "https://cdn.example.test/tshirt.jpg",
                        "product_url": "https://www.ozon.ru/product/demo-2/",
                        "characteristics": {"Материал": "Хлопок"},
                        "source": "ozon",
                        "source_domain": "ozon.ru",
                        "rating": 4.8,
                        "reviews_count": 42,
                        "relevance_score": 0.9,
                        "confidence": 0.85
                    }
                ]
            },
            ensure_ascii=False,
        )
    )
    parser = OzonParser(
        results_dir="results/test_parser_cache",
        demo_cache_path=demo_cache_path,
    )

    async def fake_mobile_html(query: str) -> MethodAttempt:
        return MethodAttempt(
            method="mobile_html",
            status="blocked",
            latency_ms=5,
            products_found=0,
            fields_completeness={
                "title": 0,
                "price": 0,
                "image": 0,
                "url": 0,
                "characteristics": 0,
            },
            http_status=403,
            error="http_403",
        )

    async def fake_mobile_browser(query: str) -> MethodAttempt:
        return MethodAttempt(
            method="mobile_browser",
            status="blocked",
            latency_ms=6,
            products_found=0,
            fields_completeness={
                "title": 0,
                "price": 0,
                "image": 0,
                "url": 0,
                "characteristics": 0,
            },
            http_status=403,
            error="http_403",
        )

    monkeypatch.setattr(parser, "_search_mobile_html", fake_mobile_html)
    monkeypatch.setattr(parser, "_search_mobile_browser", fake_mobile_browser)

    result = await parser.search("футболка мужская хлопок", use_cache=False)

    assert result.method_used == "demo_cache"
    assert result.status == "cached"
    assert result.is_cached is True
    assert len(result.products) == 1

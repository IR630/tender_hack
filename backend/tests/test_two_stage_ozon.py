from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.scrapers.two_stage_ozon import TwoStageOzonParser


@pytest.mark.asyncio
async def test_two_stage_pipeline_search() -> None:
    search_html = """
    <div data-widget="tileGridDesktop">
      <div class="tile-root">
        <a href="/product/printer-hp-1/"><span class="tsBody500Medium">Принтер HP LaserJet</span></a>
        <img srcset="https://ir.ozone.ru/s3/multimedia-1-q/wc1000/1.jpg 2x">
        <span>12 481 ₽</span>
      </div>
      <div class="tile-root">
        <a href="/product/shoes-nike-2/"><span class="tsBody500Medium">Кроссовки Nike Air</span></a>
        <img srcset="https://ir.ozone.ru/s3/multimedia-1-q/wc1000/2.jpg 2x">
        <span>8 500 ₽</span>
      </div>
    </div>
    """
    product_html = """
    <script type="application/ld+json">
    {"@type":"Product","description":"Лазерный принтер для офиса.","additionalProperty":[{"name":"Бренд","value":"HP"}]}
    </script>
    """

    async def fake_pipeline(label, handler, timeout_seconds=None):
        products, error = await handler(object())
        return products, error

    parser = TwoStageOzonParser()
    navigate_mock = AsyncMock(
        side_effect=[
            (search_html, None),
            (product_html, None),
        ]
    )

    with (
        patch("app.scrapers.two_stage_ozon.ozon_browser.run_browser_pipeline", side_effect=fake_pipeline),
        patch("app.scrapers.two_stage_ozon.ozon_browser.navigate_and_get_html", navigate_mock),
        patch(
            "app.scrapers.two_stage_ozon.filter_top_k_by_similarity",
            side_effect=lambda query, products, top_k=5: products[:top_k],
        ),
        patch("app.scrapers.two_stage_ozon.settings.ozon_enrich_enabled", True),
        patch("app.scrapers.two_stage_ozon.settings.ozon_enrich_delay_seconds", 0),
        patch("app.scrapers.two_stage_ozon.settings.ozon_browser_cache_enabled", False),
        patch("app.scrapers.two_stage_ozon.settings.ozon_broad_search_max", 36),
        patch("app.scrapers.two_stage_ozon.settings.ozon_ml_top_k", 1),
    ):
        products, error, status = await parser.search("принтер hp", skip_cache=True)

    assert error is None
    assert status is None
    assert len(products) == 1
    assert "HP LaserJet" in products[0]["title"]
    assert products[0]["description"] and "офиса" in products[0]["description"]
    assert "• Бренд: HP" in products[0]["description"]
    assert products[0]["characteristics"].get("Бренд") == "HP"
    assert navigate_mock.await_count == 2

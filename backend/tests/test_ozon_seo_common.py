from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.scrapers.ozon_ml_filter import filter_top_k_by_similarity
from app.scrapers.ozon_seo_common import extract_broad_search_products, extract_product_enrichment

SAMPLE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ozon_search_tile_sample.html"


def test_extract_broad_search_from_tile_cards() -> None:
    html = SAMPLE.read_text(encoding="utf-8")
    products = extract_broad_search_products(html, max_results=10)

    assert len(products) >= 2
    first = products[0]
    assert "HP DeskJet 2320" in first["title"]
    assert first["price"] > 0
    assert first["url"].startswith("https://www.ozon.ru/product/")
    assert first["image"] and "wc1000" in first["image"]
    assert first["description"] is None
    assert first["characteristics"] == {}
    assert all("баллов за отзыв" not in p["title"].lower() for p in products)


def test_extract_broad_search_ignores_recommendation_widget() -> None:
    html = """
    <div data-widget="tileGridDesktop">
      <div class="tile-root">
        <a href="/product/main-grid-item-1/">
          <span class="tsBody500Medium">Основной товар HP</span>
        </a>
        <img srcset="https://ir.ozone.ru/s3/multimedia-1-q/wc1000/111.jpg 2x">
        <span>5 062 ₽</span>
      </div>
    </div>
    <div data-widget="sponsoredProducts">
      <div class="tile-root">
        <a href="/product/ad-item-999/"><span class="tsBody500Medium">Реклама мусор</span></a>
        <span>999 ₽</span>
      </div>
    </div>
    """
    products = extract_broad_search_products(html, max_results=10)
    assert len(products) == 1
    assert products[0]["title"] == "Основной товар HP"


def test_extract_product_enrichment_from_og_description() -> None:
    html = """
    <head>
      <meta property="og:description"
            content="Полное описание смартфона Apple iPhone 15 для офиса и дома.">
    </head>
    <div data-widget="webCharacteristics">
      <tr><td>Бренд</td><td>Apple</td></tr>
    </div>
    """
    detail = extract_product_enrichment(html)
    assert "iPhone 15" in detail["description"]

    html = """
    <script type="application/ld+json">
    {
      "@type": "Product",
      "name": "Принтер HP",
      "description": "Полное описание принтера для офиса и дома.",
      "additionalProperty": [
        {"name": "Бренд", "value": "HP"},
        {"name": "Вес", "value": "4.5 кг"}
      ]
    }
    </script>
    """
    detail = extract_product_enrichment(html)
    assert "офиса" in detail["description"]
    assert detail["characteristics"]["Бренд"] == "HP"
    assert detail["characteristics"]["Вес"] == "4.5 кг"


def test_ml_filter_returns_top_k() -> None:
    products = [
        {"title": "Кроссовки Nike Air", "price": 10000, "url": "https://www.ozon.ru/product/a/"},
        {"title": "Принтер HP LaserJet", "price": 20000, "url": "https://www.ozon.ru/product/b/"},
        {"title": "Футболка Adidas", "price": 30000, "url": "https://www.ozon.ru/product/c/"},
    ]

    class FakeModel:
        def encode(self, texts, normalize_embeddings=True):
            vectors = {
                "принтер hp": [1.0, 0.0],
                "Кроссовки Nike Air": [0.0, 1.0],
                "Принтер HP LaserJet": [1.0, 0.0],
                "Футболка Adidas": [0.0, 1.0],
            }
            import numpy as np

            return np.array([vectors[t] for t in texts], dtype=float)

    with patch("app.scrapers.ozon_ml_filter._get_model", return_value=FakeModel()):
        top = filter_top_k_by_similarity("принтер hp", products, top_k=1)

    assert len(top) == 1
    assert "LaserJet" in top[0]["title"]
    assert top[0]["similarity"] == 1.0

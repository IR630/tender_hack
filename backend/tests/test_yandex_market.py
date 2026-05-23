import pytest
from selectolax.parser import HTMLParser

from app.core.models import Product, SearchRequest
from app.scrapers.yandex_market import (
    _build_description,
    _clean_title_text,
    _collect_paginated_products,
    _extract_characteristics,
    _is_garbage_listing,
    _is_similar_title,
    _parse_card_prose,
    _parse_card_specs,
    _parse_search_html,
    _parse_snippet_title,
)

SAMPLE_HTML = """
<html><body>
<article>
  <a href="/card/iphone-15/123">
    <img src="https://avatars.mds.yandex.net/get-mpic/1.jpeg/orig" />
    <span data-auto="snippet-title">Смартфон Apple iPhone 15 128 ГБ, Dual: nano SIM, черный</span>
    <span data-auto="snippet-price-current">47 746 ₽</span>
    <span data-auto="reviews">4.8(120) · 591 купили</span>
    <span data-auto="delivery-wrapper">29 мая, ПВЗ</span>
  </a>
</article>
</body></html>
"""

DUPLICATE_HTML = """
<html><body>
<article>
  <a href="/card/iphone-15/123-dup">
    <img src="https://avatars.mds.yandex.net/get-mpic/2.jpeg/orig" />
    <span data-auto="snippet-title">Смартфон Apple iPhone 15 128 ГБ Dual nano SIM черный</span>
    <span data-auto="snippet-price-current">48 000 ₽</span>
  </a>
</article>
</body></html>
"""

GARBAGE_HTML = """
<html><body>
<article>
  <a href="/card/case/999">
    <img src="https://avatars.mds.yandex.net/get-mpic/3.jpeg/orig" />
    <span data-auto="snippet-title">Чехол для iPhone 15 прозрачный силиконовый</span>
    <span data-auto="snippet-price-current">590 ₽</span>
  </a>
</article>
</body></html>
"""


BRAND_TITLE_HTML = """
<html><body>
<article>
  <a href="/card/trusy-fuka/1">
    <img src="https://avatars.mds.yandex.net/get-mpic/4.jpeg/orig" />
    <p data-auto="snippet-title" title="FUKA&amp;nbsp;Трусы, комплект">
      <span data-auto="snippet-brand-title">FUKA</span>Трусы, комплект
    </p>
    <span data-auto="snippet-price-current">593 ₽</span>
  </a>
</article>
</body></html>
"""


def _product_html(title: str, href: str, price: str = "10 000 ₽") -> str:
    return f"""
    <html><body>
    <article>
      <a href="{href}">
        <img src="https://avatars.mds.yandex.net/get-mpic/x.jpeg/orig" />
        <span data-auto="snippet-title">{title}</span>
        <span data-auto="snippet-price-current">{price}</span>
      </a>
    </article>
    </body></html>
    """


CARD_HTML = """
<html><body>
<div data-auto="product-description">
  Полноценный смартфон ASUS ROG Phone 9 FE с AMOLED экраном 6.78 дюйма и защитой IP68.
</div>
<div data-auto="specs-list-fullExtended">
  <div><div><span data-auto="product-spec">Бренд</span></div><div>ASUS</div></div>
  <div><div><span data-auto="product-spec">Диагональ экрана</span></div><div>6.78"</div></div>
  <div><div><span data-auto="product-spec">Встроенная память</span></div><div>512 ГБ</div></div>
  <div><div><span data-auto="product-spec">Оперативная память</span></div><div>12 ГБ</div></div>
  <div><div><span data-auto="product-spec">Операционная система</span></div>
  <div>Android 15</div></div>
</div>
</body></html>
"""


def test_parse_card_page_extracts_full_description() -> None:
    specs = _parse_card_specs(CARD_HTML)
    prose = _parse_card_prose(CARD_HTML)

    assert prose.startswith("Полноценный смартфон ASUS")
    assert specs["Бренд"] == "ASUS"
    assert specs["Диагональ экрана"] == '6.78"'
    assert specs["Встроенная память"] == "512 ГБ"

    description = _build_description(
        prose=prose,
        characteristics=specs,
        rating=4.9,
        reviews_count=194,
        bought_count=194,
        delivery="Завтра, ПВЗ",
    )
    assert "Полноценный смартфон ASUS" in description
    assert "• Бренд: ASUS" in description
    assert "• Операционная система: Android 15" in description
    assert "Рейтинг: 4.9 (194 отзывов)" in description


def test_parse_search_html_extracts_product() -> None:
    products = _parse_search_html(SAMPLE_HTML)
    assert len(products) == 1
    product = products[0]
    assert product.source == "yandex_market"
    assert "iPhone 15" in product.title
    assert product.price == 4_774_600
    assert product.image_url.startswith("https://avatars.mds.yandex.net")
    assert product.product_url.endswith("/card/iphone-15/123")
    assert product.rating == 4.8
    assert product.reviews_count == 120
    assert "128 ГБ" in product.description
    assert "591" in product.description
    assert "29 мая" in product.description


def test_parse_snippet_title_uses_title_attribute() -> None:
    tree = HTMLParser(BRAND_TITLE_HTML)
    title_el = tree.css_first('[data-auto="snippet-title"]')
    assert title_el is not None
    assert _parse_snippet_title(title_el) == "FUKA Трусы, комплект"

    products = _parse_search_html(BRAND_TITLE_HTML)
    assert len(products) == 1
    assert products[0].title == "FUKA Трусы, комплект"


def test_clean_title_text_fixes_glued_brand_fallback() -> None:
    assert _clean_title_text("BORNERSТрусы боксеры") == "BORNERS Трусы боксеры"
    assert _clean_title_text("Трусы  , комплект") == "Трусы , комплект"


def test_extract_characteristics_from_title() -> None:
    chars = _extract_characteristics("Смартфон Apple iPhone 15 128 ГБ, Dual: nano SIM, черный")
    assert chars["memory"] == "128 ГБ"
    assert "variant" in chars


def test_is_similar_title() -> None:
    left = "Смартфон Apple iPhone 15 128 ГБ, Dual: nano SIM, черный"
    right = "Смартфон Apple iPhone 15 128 ГБ Dual nano SIM черный"
    assert _is_similar_title(left, right) is True
    different_variant = "Смартфон Apple iPhone 15 128 ГБ, Dual: nano SIM + eSIM, Синий"
    assert _is_similar_title(left, different_variant) is False
    assert _is_similar_title(left, "Samsung Galaxy S24 Ultra 256 GB") is False


def test_is_garbage_listing() -> None:
    assert _is_garbage_listing("Чехол для iPhone 15", "iphone 15") is True
    assert _is_garbage_listing("Смартфон Apple iPhone 15 128 GB", "iphone 15") is False
    assert _is_garbage_listing("Набор отверток Bosch", "iphone 15") is True


def test_collect_paginated_products_stops_on_duplicates() -> None:
    pages = {
        1: SAMPLE_HTML,
        2: DUPLICATE_HTML,
        3: DUPLICATE_HTML,
        4: DUPLICATE_HTML,
        5: DUPLICATE_HTML,
        6: DUPLICATE_HTML,
    }

    def fetch(page: int) -> str:
        return pages.get(page, "")

    products = _collect_paginated_products(fetch, "iphone 15", max_pages=10)
    assert len(products) == 1
    assert products[0].title.startswith("Смартфон Apple iPhone 15")


def test_collect_paginated_products_stops_on_garbage() -> None:
    pages = {
        1: SAMPLE_HTML,
        2: GARBAGE_HTML,
        3: GARBAGE_HTML,
        4: GARBAGE_HTML,
    }

    def fetch(page: int) -> str:
        return pages.get(page, "")

    products = _collect_paginated_products(fetch, "iphone 15", max_pages=10)
    assert len(products) == 1


def test_collect_paginated_products_keeps_going_while_relevant() -> None:
    pages = {
        1: _product_html("Смартфон Apple iPhone 15 128 GB черный", "/card/iphone-15-128-black"),
        2: _product_html("Смартфон Apple iPhone 15 256 GB синий", "/card/iphone-15-256-blue"),
        3: _product_html("Смартфон Apple iPhone 15 512 GB белый", "/card/iphone-15-512-white"),
    }

    def fetch(page: int) -> str:
        return pages.get(page, "")

    products = _collect_paginated_products(fetch, "iphone 15", max_pages=10)
    assert len(products) == 3


@pytest.mark.asyncio
async def test_yandex_market_search_uses_cache(monkeypatch) -> None:
    from app.scrapers import yandex_market as ym

    cached = [
        Product(
            source="yandex_market",
            source_domain="market.yandex.ru",
            title="Трусы FUKA, комплект",
            description="cached",
            price=59_300,
            image_url="https://example.com/1.jpg",
            product_url="https://market.yandex.ru/card/1",
        )
    ]

    async def fake_load(region, query):
        return cached

    async def fail_fetch(*args, **kwargs):
        raise AssertionError("fetch should not run on cache hit")

    monkeypatch.setattr(ym, "_load_cached_products", fake_load)
    monkeypatch.setattr(ym, "_fetch_products_sync", fail_fetch)

    products = await ym.scraper.search(SearchRequest(query="трусы", region="moscow"))
    assert products == cached


@pytest.mark.integration
@pytest.mark.asyncio
async def test_yandex_market_live_search() -> None:
    from app.scrapers.yandex_market import scraper

    products = await scraper.search(SearchRequest(query="телефон asus"))
    assert len(products) >= 1
    assert all(product.price > 0 for product in products)
    assert all(product.product_url.startswith("https://market.yandex.ru") for product in products)
    assert any(len(product.description) > 200 for product in products)
    assert any(len(product.characteristics) >= 5 for product in products)

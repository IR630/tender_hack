from other_public_scraper.parsers.listing_grid import extract_dom_listing_products
from other_public_scraper.pipelines.page_extractor import extract_products_from_listing_html

DNS_LISTING_HTML = """
<html><body>
<div class="catalog-product">
  <a class="catalog-product__image-link" href="/product/abc123/mys-logitech-b100/">
    <img src="https://c.dns-shop.ru/thumb/test.jpg">
  </a>
  <a class="catalog-product__name" href="/product/abc123/mys-logitech-b100/">
    Мышь проводная Logitech B100
  </a>
  <div class="catalog-product__price">
    <div class="product-buy__price">590 ₽</div>
  </div>
</div>
<div class="catalog-product">
  <a class="catalog-product__name" href="/product/def456/mys-besprovodnaa/">
    Мышь беспроводная Test M100
  </a>
  <div class="catalog-product__price" data-product-price="1290">1 290 ₽</div>
</div>
</body></html>
"""


TECHNOCITY_LISTING_HTML = """
<html><body>
<article class="catalog-item item" id="item547489">
  <a href="/catalog/detail/547489/">
    <span class="name">Мышь Logitech OEM B100 Black</span>
  </a>
  <div class="price-above-button">650</div>
</article>
</body></html>
"""


def test_extract_technocity_dom_listing():
    items = extract_dom_listing_products(
        TECHNOCITY_LISTING_HTML,
        "https://www.technocity.ru/catalog/13/proizvoditel--logitech/",
        max_items=10,
    )
    assert len(items) == 1
    assert items[0]["price_rub"] == 650
    assert "Logitech" in items[0]["title"]


def test_extract_dns_dom_listing():
    items = extract_dom_listing_products(
        DNS_LISTING_HTML,
        "https://www.dns-shop.ru/catalog/17a8a69116404e77/mysi/",
        max_items=10,
    )
    assert len(items) == 2
    assert items[0]["price_rub"] == 590
    assert "Logitech" in items[0]["title"]


def test_extract_products_from_listing_html_uses_dom():
    items = extract_products_from_listing_html(
        DNS_LISTING_HTML,
        "https://www.dns-shop.ru/catalog/17a8a69116404e77/mysi/",
        max_items=10,
    )
    assert len(items) == 2
    assert items[0].extraction_method == "dom_listing"
    assert items[0].source_domain == "dns-shop.ru"

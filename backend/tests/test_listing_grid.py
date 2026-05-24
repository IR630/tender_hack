from other_public_scraper.parsers.listing_grid import extract_dom_listing_products
from other_public_scraper.pipelines.page_extractor import extract_products_from_listing_html
from other_public_scraper.scraper import _is_listing_grid_url

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

E2E4_LISTING_HTML = """
<html><body>
<div class="block-offer-item catalog-page-offer subcategory-new-offers__item-block">
  <a href="/catalog/item/mysh-logitech-b100-usb-chernyy-910-003357-910-006605-393606/" class="block-offer-item__image">
    <img src="https://imgproxy.e2e4.ru/100x100/3162784">
  </a>
  <div class="block-offer-item__info">
    <a href="/catalog/item/mysh-logitech-b100-usb-chernyy-910-003357-910-006605-393606/" class="block-offer-item__name">
      Мышь Logitech B100, USB, черный
    </a>
    <div class="block-offer-item__reference-id">Код: 393606</div>
  </div>
  <div class="price-block block-offer-item__price _default">
    <div class="price-block__price _IN_PLACE"><span>485&nbsp;₽</span></div>
  </div>
</div>
</body></html>
"""

CITILINK_LISTING_HTML = """
<html><body>
<div data-meta-name="SnippetProductVerticalLayout" data-meta-product-id="2070314">
  <a href="/product/mysh-oklik-202mw-chernyi-optich-1000dpi-besprov-usb-3but-2070314-2070314/"
     title="Мышь беспроводная Oklick 202MW, радио, оптическая, 1000dpi, черный [2070314]"></a>
  <img src="https://cdn.citilink.ru/test.jpg" alt="Мышь беспроводная Oklick">
  <span data-meta-price="455">455 ₽</span>
  <a href="/product/mysh-oklik-202mw-chernyi-optich-1000dpi-besprov-usb-3but-2070314-2070314/otzyvy/">4.9 20</a>
</div>
</body></html>
"""

GENERIC_LOW_PRICE_LISTING_HTML = """
<html><body>
<div class="item">
  <a href="/product/trusy-flag-set/">Набор мужских трусов CK FLAG 5 штук 3 694 руб.</a>
  <a href="/product/trusy-flag-110/">Мужские трусы CK Flag 110 Материал: 95% ХЛОПОК 5% ЛАЙКРА 699 руб.</a>
  <div>1 ₽</div>
  <img src="https://supertrus.ru/test.jpg">
</div>
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


def test_extract_e2e4_dom_listing_price_does_not_include_product_code():
    items = extract_dom_listing_products(
        E2E4_LISTING_HTML,
        "https://novosibirsk.e2e4online.ru/catalog/myshi-18/",
        max_items=10,
    )
    assert len(items) == 1
    assert items[0]["price_rub"] == 485
    assert items[0]["product_url"].endswith("-393606/")


def test_extract_citilink_dom_listing_skips_review_links():
    items = extract_dom_listing_products(
        CITILINK_LISTING_HTML,
        "https://www.citilink.ru/catalog/myshi/",
        max_items=10,
    )
    assert len(items) == 1
    assert items[0]["price_rub"] == 455
    assert "/otzyvy/" not in items[0]["product_url"]


def test_generic_dom_listing_ignores_suspicious_one_ruble_price():
    items = extract_dom_listing_products(
        GENERIC_LOW_PRICE_LISTING_HTML,
        "https://supertrus.ru/catalog/",
        max_items=10,
    )

    assert len(items) == 2
    assert items[0]["price_rub"] == 3694
    assert items[1]["price_rub"] == 699


def test_generic_dom_listing_price_does_not_include_model_number():
    html = """
    <html><body>
    <div>
      <a href="/product/premiata-quinn-8245/">
        Premiata Мужские кроссовки Quinn 8245 35 490 ₽ по 8 872 ₽ x4 платежами
      </a>
      <img src="https://brandshop.ru/test.jpg">
    </div>
    </body></html>
    """

    items = extract_dom_listing_products(
        html,
        "https://brandshop.ru/catalog/muzhskie-krossovki/",
        max_items=10,
    )

    assert len(items) == 1
    assert items[0]["price_rub"] == 35490


def test_extract_products_from_listing_html_uses_dom():
    items = extract_products_from_listing_html(
        DNS_LISTING_HTML,
        "https://www.dns-shop.ru/catalog/17a8a69116404e77/mysi/",
        max_items=10,
    )
    assert len(items) == 2
    assert items[0].extraction_method == "dom_listing"
    assert items[0].source_domain == "dns-shop.ru"


def test_e2e4_mouse_catalog_is_listing_grid():
    assert _is_listing_grid_url("https://novosibirsk.e2e4online.ru/catalog/myshi-18/")

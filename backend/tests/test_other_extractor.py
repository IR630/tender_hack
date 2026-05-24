from other_public_scraper.pipelines.page_extractor import (
    extract_product_from_html,
    extract_products_from_listing_html,
    is_category_listing,
    is_product_page_url,
)

JSON_LD_HTML = """
<html><head>
<script type="application/ld+json">{
  "@type": "Product",
  "name": "Ноутбук Test",
  "description": "Описание ноутбука",
  "image": "https://shop.example/img.jpg",
  "offers": {"price": "64990", "priceCurrency": "RUB"}
}</script>
<meta property="og:image" content="https://shop.example/img.jpg" />
</head><body></body></html>
"""


def test_extract_product_from_json_ld():
    item = extract_product_from_html(
        JSON_LD_HTML,
        "https://dns-shop.ru/product/test-123/",
        relevance_score=0.9,
    )
    assert item is not None
    assert item.title == "Ноутбук Test"
    assert item.description == "Описание ноутбука"
    assert item.price_rub == 64990
    assert item.image_url.startswith("https://")


def test_extract_product_replaces_suspicious_one_ruble_price():
    html = """
    <html><head>
      <meta property="og:title" content="Мужские трусы CK Flag 110 Материал: 95% ХЛОПОК 5% ЛАЙКРА 699 руб.">
      <meta property="og:description" content="Мужские трусы CK Flag 110 Материал: 95% ХЛОПОК 5% ЛАЙКРА 699 руб.">
      <meta property="product:price:amount" content="1">
      <meta property="og:image" content="https://fit-trus.ru/test.jpg">
    </head><body>
      <div>Открыть на маркетплейсе 1 ₽</div>
      <div>Мужские трусы CK Flag 110 Материал: 95% ХЛОПОК 5% ЛАЙКРА 699 руб.</div>
    </body></html>
    """

    item = extract_product_from_html(html, "https://fit-trus.ru/product/test/")

    assert item is not None
    assert item.price_rub == 699


LISTING_HTML = """
<html><head>
<script type="application/ld+json">{
  "@type": "ItemList",
  "itemListElement": [
    {"@type": "ListItem", "position": 1, "item": {
      "@type": "Product", "name": "Шина A", "image": "https://shop.example/a.jpg",
      "url": "https://koleso.ru/p/a",
      "offers": {"price": "5000", "priceCurrency": "RUB"}
    }},
    {"@type": "ListItem", "position": 2, "item": {
      "@type": "Product", "name": "Шина B", "image": "https://shop.example/b.jpg",
      "url": "https://koleso.ru/p/b",
      "offers": {"price": "6000", "priceCurrency": "RUB"}
    }}
  ]
}</script>
</head><body></body></html>
"""


def test_extract_products_from_listing_html():
    items = extract_products_from_listing_html(
        LISTING_HTML,
        "https://koleso.ru/catalog/tyres/leto/",
        max_items=10,
    )
    assert len(items) == 2
    assert items[0].price_rub == 5000
    assert items[1].product_url.endswith("/p/b")


def test_is_category_listing():
    assert is_category_listing(
        "Летние шины купить от 2430 руб в Москве",
        "https://koleso.ru/catalog/tyres/leto/",
    )
    assert not is_category_listing(
        "Nokian Hakka Blue 2 205/55 R16",
        "https://koleso.ru/catalog/tyres/leto/nokian/12345/",
    )
    assert not is_category_listing(
        "AIR OPTIX PLUS HYDRAGLYDE (3 линзы)",
        "https://ochkarik.ru/catalog/kontaktnye-linzy/air-optix-plus-hydraglyde-3-linzy/382335/",
    )
    assert is_product_page_url(
        "https://ochkarik.ru/catalog/kontaktnye-linzy/air-optix-plus-hydraglyde-3-linzy/382335/"
    )
    assert not is_category_listing(
        "Кроссовки Jomoto купить по цене 1199 ₽ в интернет-магазине",
        "https://www.detmir.ru/product/index/id/6745611/",
    )
    assert is_product_page_url(
        "https://novosibirsk.beeline.ru/shop/details/mysh-provodnaya-logitech-m90-black/"
    )
    assert not is_category_listing(
        "Купить Мышь Logitech M90 Чёрная по выгодной цене в интернет-магазине билайн",
        "https://novosibirsk.beeline.ru/shop/details/mysh-provodnaya-logitech-m90-black/",
    )
    assert not is_product_page_url("https://novosibirsk.e2e4online.ru/catalog/myshi-18/")

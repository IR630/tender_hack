from other_public_scraper.pipelines.page_extractor import extract_product_from_html

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

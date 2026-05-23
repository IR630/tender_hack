from other_public_scraper.parsers.adapters.notik import adapter


def test_notik_adapter_absolute_image():
    html = """
    <html><head><title>Test</title></head><body>
    <meta itemprop="price" content="123456">
    <img src="/img/catalog_img/1/big/photo.jpg">
    </body></html>
    """
    raw = adapter.extract(html, "https://www.notik.ru/goods/test.htm")
    assert raw["price_rub"] == 123456
    assert raw["image_url"].startswith("https://www.notik.ru/")

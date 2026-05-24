from other_public_scraper.pipelines.catalog_harvest import _extract_links


def test_extract_links_treats_model_catalog_as_catalog_seed_not_product():
    html = """
    <html><body>
      <a href="/catalog/iphone-16/">iPhone 16 catalog</a>
      <a href="/product/abc123/iphone-16-128gb-black/">iPhone 16 128GB black</a>
    </body></html>
    """

    products, catalogs = _extract_links(html, "https://www.re-store.ru/")

    assert "https://www.re-store.ru/product/abc123/iphone-16-128gb-black/" in products
    assert "https://www.re-store.ru/catalog/iphone-16/" in catalogs
    assert "https://www.re-store.ru/catalog/iphone-16/" not in products

from app.utils.image_urls import is_allowed_image_host, normalize_marketplace_image_url


def test_normalize_yandex_market_image_to_orig() -> None:
    url = (
        "https://avatars.mds.yandex.net/get-mpic/15422059/"
        "2a0000019ad9c64de8f919f3fc570eb5ad14/120x160_multiply"
    )
    assert normalize_marketplace_image_url(url).endswith("/orig")


def test_normalize_other_image_urls_unchanged() -> None:
    url = "https://ir.ozone.ru/s3/multimedia-1-f/wc1000/9927237615.jpg"
    assert normalize_marketplace_image_url(url) == url


def test_is_allowed_image_host_for_source_domain_cdn() -> None:
    url = "https://cdn.digital-razor.ru/path/product.webp"
    assert is_allowed_image_host(url, source_domain="digital-razor.ru") is True
    assert is_allowed_image_host(url) is False

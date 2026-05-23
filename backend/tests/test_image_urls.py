from app.utils.image_urls import normalize_marketplace_image_url


def test_normalize_yandex_market_image_to_orig() -> None:
    url = (
        "https://avatars.mds.yandex.net/get-mpic/15422059/"
        "2a0000019ad9c64de8f919f3fc570eb5ad14/120x160_multiply"
    )
    assert normalize_marketplace_image_url(url).endswith("/orig")


def test_normalize_other_image_urls_unchanged() -> None:
    url = "https://ir.ozone.ru/s3/multimedia-1-f/wc1000/9927237615.jpg"
    assert normalize_marketplace_image_url(url) == url

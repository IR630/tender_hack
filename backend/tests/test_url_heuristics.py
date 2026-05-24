from other_public_scraper.models import UrlCandidate
from other_public_scraper.url_heuristics import (
    filter_and_sort_candidates,
    is_rejected_url,
    url_quality_score,
)


def test_reject_compare_and_foreign_urls():
    assert is_rejected_url("https://www.apple.com/de/iphone")
    assert is_rejected_url("https://www.gsmarena.com/compare.php3?id=1")
    assert is_rejected_url("https://www.mediamarkt.de/de/brand/apple/iphone")
    assert is_rejected_url("https://chip.de/artikel/iPhone-Vergleich")
    assert not is_rejected_url("https://www.dns-shop.ru/product/abc123/smartfon")


def test_prefer_ru_product_urls():
    candidates = [
        UrlCandidate(url="https://www.apple.com/sg/iphone/compare", domain="apple.com", title="Compare"),
        UrlCandidate(
            url="https://www.dns-shop.ru/product/abc/smartfon-apple-iphone-se",
            domain="dns-shop.ru",
            title="iPhone SE",
        ),
        UrlCandidate(
            url="https://re-store.ru/smartfony/apple/iphone-se/",
            domain="re-store.ru",
            title="iPhone SE каталог",
        ),
    ]
    filtered = filter_and_sort_candidates(candidates)
    assert filtered[0].domain == "dns-shop.ru"
    assert all(not is_rejected_url(c.url) for c in filtered)


def test_url_quality_product_beats_catalog():
    product = url_quality_score("https://citilink.ru/product/iphone-se-123/")
    catalog = url_quality_score("https://re-store.ru/smartfony/apple/iphone-se/")
    assert product > catalog

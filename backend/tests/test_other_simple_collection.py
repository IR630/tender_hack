from other_public_scraper.models import OtherExtractResult
from other_public_scraper.scraper import (
    _accept_listing_products,
    _cap_per_domain,
    _is_title_relevant_to_query,
)


def _item(domain: str, index: int, title: str = "Any product") -> OtherExtractResult:
    return OtherExtractResult(
        title=f"{title} {index}",
        price_rub=100 + index,
        image_url="https://example.com/img.jpg",
        product_url=f"https://{domain}/product/{index}/",
        source_domain=domain,
        relevance_score=float(index),
    )


def test_cap_per_domain_keeps_top_five_even_for_single_domain():
    products = [_item("shop.example", index) for index in range(8)]

    capped = _cap_per_domain(products, max_total=15, hard_cap_per_domain=5)

    assert len(capped) == 5
    assert {item.source_domain for item in capped} == {"shop.example"}


def test_accept_listing_products_filters_by_query_relevance():
    listing = [
        _item("shop-a.example", 1, title="Трусы мужские хлопковые"),
        _item("shop-a.example", 2, title="Сумка пляжная мультиколор"),
        _item("shop-a.example", 3, title="Добавить товар"),
    ]

    accepted = _accept_listing_products(listing, "трусы", seen=set())

    assert [item.product_url for item in accepted] == [
        "https://shop-a.example/product/1/",
    ]


def test_title_relevance_supports_aliases_and_numbers():
    assert _is_title_relevant_to_query("Боксеры мужские хлопковые", "трусы")
    assert not _is_title_relevant_to_query("Сумка пляжная Ysabel Mora", "трусы")
    assert _is_title_relevant_to_query("Apple iPhone 15 128GB Black", "iphone 15")
    assert not _is_title_relevant_to_query("Apple iPhone 16 128GB Black", "iphone 15")

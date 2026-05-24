from other_public_scraper.query_variants import search_query_variants


def test_iphone_se_variant():
    variants = search_query_variants("iphone 10 se")
    assert variants[:2] == ["iphone 10 se", "iphone se"]
    assert "iphone 10 se купить" in variants
    assert search_query_variants("ноутбук") == [
        "ноутбук",
        "ноутбук купить",
        "ноутбук цена",
        "ноутбук интернет-магазин",
    ]


def test_cyrillic_iphone_variant():
    variants = search_query_variants("айфон 15")
    assert "айфон 15" in variants
    assert "iphone 15" in variants
    assert any("Apple" in v for v in variants)


def test_optics_variants():
    variants = search_query_variants("очки")
    assert "очки" in variants
    assert "очки купить" in variants
    assert "оправы для очков" in variants

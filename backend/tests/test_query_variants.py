from other_public_scraper.query_variants import search_query_variants


def test_iphone_se_variant():
    variants = search_query_variants("iphone 10 se")
    assert variants == ["iphone 10 se", "iphone se"]
    assert search_query_variants("ноутбук") == ["ноутбук"]

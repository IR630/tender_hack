from ozon_public_scraper.parsers.price import parse_price


def test_price_edge_cases():
    assert parse_price("1\u202f299\u202f000") == 1299000
    assert parse_price("1750.00") == 1750
    assert parse_price("abc") is None
    assert parse_price("0") is None

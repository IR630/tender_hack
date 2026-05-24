from other_public_scraper.orgtech_seeds import orgtech_seed_candidates


def test_orgtech_mouse_seeds_include_e2e4_catalog():
    urls = [candidate.url for candidate in orgtech_seed_candidates("мышка", "novosibirsk")]

    assert "https://novosibirsk.e2e4online.ru/catalog/myshi-18/" in urls
    assert "https://www.dns-shop.ru/catalog/17a8a69116404e77/mysi/" in urls
    assert "https://www.citilink.ru/catalog/myshi/" in urls


def test_orgtech_mouse_seeds_use_requested_region():
    urls = [candidate.url for candidate in orgtech_seed_candidates("мышка", "moscow")]

    assert "https://moscow.e2e4online.ru/catalog/myshi-18/" in urls
    assert "https://novosibirsk.e2e4online.ru/catalog/myshi-18/" not in urls


def test_orgtech_unknown_query_has_no_broad_seed():
    assert orgtech_seed_candidates("что-нибудь полезное") == []

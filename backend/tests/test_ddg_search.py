from urllib.parse import quote

from other_public_scraper.pipelines.ddg_search import _parse_ddg_html, _resolve_ddg_href


def test_resolve_ddg_href_direct():
    assert _resolve_ddg_href("https://www.dns-shop.ru/catalog/") == (
        "https://www.dns-shop.ru/catalog/"
    )


def test_resolve_ddg_href_uddg():
    target = "https://www.citilink.ru/catalog/noutbuki/"
    wrapped = f"https://duckduckgo.com/l/?uddg={quote(target, safe='')}"
    assert _resolve_ddg_href(wrapped) == target


def test_parse_ddg_html_filters_blacklisted_domains():
    html = """
    <a class="result-link" href="https://www.dns-shop.ru/catalog/noutbuki/">DNS</a>
    <a class="result-link" href="https://www.ozon.ru/product/1">Ozon</a>
    <a class="result-link" href="https://www.citilink.ru/catalog/noutbuki/">Citilink</a>
    """
    hits = _parse_ddg_html(html, limit=10)
    urls = {hit.url for hit in hits}
    assert "https://www.dns-shop.ru/catalog/noutbuki/" in urls
    assert "https://www.citilink.ru/catalog/noutbuki/" in urls
    assert all("ozon.ru" not in url for url in urls)
    assert hits[0].source == "ddg"


def test_parse_ddg_html_resolves_uddg_links():
    target = "https://www.mvideo.ru/noutbuki-118"
    wrapped = f"https://duckduckgo.com/l/?uddg={quote(target, safe='')}"
    html = f'<a class="result-link" href="{wrapped}">Mvideo</a>'
    hits = _parse_ddg_html(html, limit=5)
    assert len(hits) == 1
    assert hits[0].url == target

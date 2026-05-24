import pytest

from other_public_scraper.models import UrlCandidate
from other_public_scraper.pipelines import web_search


@pytest.mark.asyncio
async def test_search_live_urls_expanded_does_not_use_site_supplements(monkeypatch):
    ddg_queries: list[str] = []

    async def fake_live(query: str, *, limit=None, allow_fallbacks=True):
        return []

    async def fake_ddg(query: str, *, limit=20):
        ddg_queries.append(query)
        return []

    monkeypatch.setattr(web_search, "search_live_urls", fake_live)
    monkeypatch.setattr(web_search, "search_ddg_urls", fake_ddg)

    await web_search.search_live_urls_expanded("мышка", category="orgtech")

    assert not any("site:" in query for query in ddg_queries)


def test_select_live_candidates_keeps_catalog_only_as_seed():
    product = UrlCandidate(
        url="https://www.citilink.ru/product/iphone-16-128gb-black-1234567/",
        domain="citilink.ru",
        title="iPhone 16 128GB black",
    )
    catalog = UrlCandidate(
        url="https://www.re-store.ru/catalog/iphone-16/",
        domain="re-store.ru",
        title="iPhone 16",
    )

    selected = web_search._select_live_candidates([catalog, product], limit=10)
    urls = [item.url for item in selected]

    assert urls[0] == product.url
    assert catalog.url in urls

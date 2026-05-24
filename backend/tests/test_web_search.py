import pytest

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

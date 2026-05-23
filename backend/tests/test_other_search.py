import pytest

from app.core.models import SearchRequest
from app.sources.other import search as other_search_module


@pytest.mark.asyncio
async def test_search_other_sources_retry_corrected(monkeypatch):
    calls: list[str] = []

    async def fake_run(query, region):
        calls.append(query)
        if query == "принтер":
            return [other_search_module._to_product(type("R", (), {
                "source_domain": "dns-shop.ru",
                "title": "Принтер",
                "description": "",
                "price_rub": 10000,
                "image_url": "https://img/1.jpg",
                "product_url": "https://dns-shop.ru/p/1",
                "characteristics": {},
                "relevance_score": 0.9,
                "confidence": 0.8,
            })())]
        return []

    monkeypatch.setattr(other_search_module, "_run_search", fake_run)
    monkeypatch.setattr(other_search_module.settings, "other_cache_enabled", False)

    products = await other_search_module.search_other_sources(
        SearchRequest(query="принтер", region="moscow"),
        original_query="прнтер",
    )
    assert len(products) == 1
    assert calls == ["прнтер", "принтер"]
    assert other_search_module.get_last_error() is None


@pytest.mark.asyncio
async def test_search_other_sources_sets_error_when_empty(monkeypatch):
    async def fake_run(query, region):
        return []

    monkeypatch.setattr(other_search_module, "_run_search", fake_run)
    monkeypatch.setattr(other_search_module.settings, "other_cache_enabled", False)
    monkeypatch.setattr(
        other_search_module,
        "get_diagnostics",
        lambda: type("D", (), {"format_user_message": lambda self: "diag: empty"})(),
    )

    products = await other_search_module.search_other_sources(
        SearchRequest(query="тест", region="moscow"),
    )
    assert products == []
    assert other_search_module.get_last_error() is not None

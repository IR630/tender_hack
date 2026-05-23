"""Coverage for the attempt-sequencing & last_error wiring in sources/other.search."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.core.models import SearchRequest
from app.sources.other import search as other_search


def _stub_item(domain: str, price: float, title: str = "t") -> Any:
    return SimpleNamespace(
        source_domain=domain,
        title=title,
        description="",
        price_rub=price,
        image_url="https://example.com/i.jpg",
        product_url=f"https://{domain}/p/1",
        characteristics={},
        relevance_score=0.5,
        confidence=0.9,
    )


@pytest.mark.asyncio
async def test_returns_results_from_first_successful_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_search_other(query: str, region: str):
        calls.append(query)
        return [_stub_item("dns.ru", 12345.0)]

    monkeypatch.setattr(other_search, "search_other", fake_search_other)
    monkeypatch.setattr(other_search.settings, "other_cache_enabled", False)

    products = await other_search.search_other_sources(
        SearchRequest(query="iphone", region="moscow"),
        original_query="iphone",
    )
    assert len(products) == 1
    assert products[0].source == "other"
    assert products[0].source_domain == "dns.ru"
    # price_rub * 100 (kopecks)
    assert products[0].price == 1234500
    assert other_search.get_last_error() is None
    assert calls == ["iphone"]


@pytest.mark.asyncio
async def test_tries_corrected_query_when_original_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_search_other(query: str, region: str):
        calls.append(query)
        if query == "iphon":
            return []
        return [_stub_item("citilink.ru", 100.0)]

    def fake_diag():
        return None

    monkeypatch.setattr(other_search, "search_other", fake_search_other)
    monkeypatch.setattr(other_search, "get_diagnostics", fake_diag)
    monkeypatch.setattr(other_search.settings, "other_cache_enabled", False)

    products = await other_search.search_other_sources(
        SearchRequest(query="iphone", region="moscow"),
        original_query="iphon",
    )
    assert calls == ["iphon", "iphone"]
    assert len(products) == 1
    assert other_search.get_last_error() is None


@pytest.mark.asyncio
async def test_deduplicates_identical_original_and_corrected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_search_other(query: str, region: str):
        calls.append(query)
        return []

    monkeypatch.setattr(other_search, "search_other", fake_search_other)
    monkeypatch.setattr(other_search, "get_diagnostics", lambda: None)
    monkeypatch.setattr(other_search.settings, "other_cache_enabled", False)

    products = await other_search.search_other_sources(
        SearchRequest(query="iphone", region="moscow"),
        original_query="iphone",
    )
    assert products == []
    assert calls == ["iphone"], "must not retry the same query twice"


@pytest.mark.asyncio
async def test_records_diagnostic_message_when_all_attempts_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search_other(query: str, region: str):
        return []

    class FakeDiag:
        def format_user_message(self) -> str:
            return "0 кандидатов из 5 поисковых движков"

    monkeypatch.setattr(other_search, "search_other", fake_search_other)
    monkeypatch.setattr(other_search, "get_diagnostics", lambda: FakeDiag())
    monkeypatch.setattr(other_search.settings, "other_cache_enabled", False)

    products = await other_search.search_other_sources(
        SearchRequest(query="iphone 15", region="moscow"),
        original_query="iphone 15",
    )
    assert products == []
    assert other_search.get_last_error() == "0 кандидатов из 5 поисковых движков"


@pytest.mark.asyncio
async def test_records_timeout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search_other(query: str, region: str):
        raise TimeoutError()

    monkeypatch.setattr(other_search, "search_other", fake_search_other)
    monkeypatch.setattr(other_search, "get_diagnostics", lambda: None)
    monkeypatch.setattr(other_search.settings, "other_cache_enabled", False)

    products = await other_search.search_other_sources(
        SearchRequest(query="iphone", region="moscow"),
        original_query="iphone",
    )
    assert products == []
    msg = other_search.get_last_error()
    assert msg is not None and "таймаут" in msg.lower()


@pytest.mark.asyncio
async def test_records_unexpected_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search_other(query: str, region: str):
        raise ValueError("bad upstream")

    monkeypatch.setattr(other_search, "search_other", fake_search_other)
    monkeypatch.setattr(other_search, "get_diagnostics", lambda: None)
    monkeypatch.setattr(other_search.settings, "other_cache_enabled", False)

    products = await other_search.search_other_sources(
        SearchRequest(query="iphone", region="moscow"),
        original_query="iphone",
    )
    assert products == []
    msg = other_search.get_last_error()
    assert msg is not None
    assert "ValueError" in msg
    assert "bad upstream" in msg


@pytest.mark.asyncio
async def test_last_error_cleared_on_success_after_prior_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Prime the module-level error from a previous failed call.
    async def boom(query: str, region: str):
        raise ValueError("first failure")

    monkeypatch.setattr(other_search, "search_other", boom)
    monkeypatch.setattr(other_search, "get_diagnostics", lambda: None)
    monkeypatch.setattr(other_search.settings, "other_cache_enabled", False)
    await other_search.search_other_sources(
        SearchRequest(query="x", region="moscow"),
        original_query="x",
    )
    assert other_search.get_last_error() is not None

    async def ok(query: str, region: str):
        return [_stub_item("dns.ru", 100.0)]

    monkeypatch.setattr(other_search, "search_other", ok)
    await other_search.search_other_sources(
        SearchRequest(query="x", region="moscow"),
        original_query="x",
    )
    assert other_search.get_last_error() is None
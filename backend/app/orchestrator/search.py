import asyncio
import logging
import time
from collections.abc import Coroutine
from typing import Any

from app.core.models import (
    Product,
    SearchGroup,
    SearchQuery,
    SearchRequest,
    SearchResponse,
    SearchSummary,
)
from app.core.config import settings
from app.core.regions import resolve_region
from app.query.processor import process_query
from app.scrapers import ozon, wb, yandex_market
from app.sources.other.search import get_last_error, search_other_sources
from app.tasks.store import search_task_store

logger = logging.getLogger(__name__)

SOURCE_DISPLAY_NAMES = {
    "wildberries": "Wildberries",
    "ozon": "Ozon",
    "yandex_market": "Яндекс Маркет",
    "other": "Другие источники",
}

SOURCE_ORDER = ("wildberries", "yandex_market", "other", "ozon")


def _enabled_sources() -> frozenset[str]:
    raw = settings.search_enabled_sources.strip()
    if not raw or raw == "*":
        return frozenset(SOURCE_ORDER)
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _active_source_order() -> tuple[str, ...]:
    enabled = _enabled_sources()
    return tuple(source for source in SOURCE_ORDER if source in enabled)


async def _safe_search(scraper, coro) -> tuple[list[Product], str | None, str | None]:
    source = getattr(scraper, "source", "unknown")
    if hasattr(scraper, "clear_error"):
        scraper.clear_error()
    try:
        products = await coro
        error = getattr(scraper, "last_error", None)
        status = getattr(scraper, "last_source_status", None) if scraper else None
        return products, error, status
    except Exception as exc:
        logger.exception("Source %r crashed during search; treating as 0 results", source)
        return [], f"{type(exc).__name__}: {exc}", None


def _build_summary(groups: list[SearchGroup]) -> SearchSummary:
    prices = [
        product.price
        for group in groups
        for product in group.products
        if product.price > 0
    ]
    if not prices:
        return SearchSummary()

    sorted_prices = sorted(prices)
    mid = len(sorted_prices) // 2
    median = (
        sorted_prices[mid]
        if len(sorted_prices) % 2
        else (sorted_prices[mid - 1] + sorted_prices[mid]) // 2
    )
    return SearchSummary(
        total_found=len(prices),
        min_price=sorted_prices[0],
        median_price=median,
        max_price=sorted_prices[-1],
    )


def _build_group(
    source: str,
    products: list[Product],
    error: str | None = None,
    status: str | None = None,
) -> SearchGroup:
    min_price = min((product.price for product in products), default=None)
    domains = sorted({product.source_domain for product in products if product.source_domain})
    return SearchGroup(
        source=source,  # type: ignore[arg-type]
        display_name=SOURCE_DISPLAY_NAMES[source],
        count=len(products),
        min_price=min_price,
        domains=domains,
        products=products,
        error=error,
        status=status,
    )


def _build_response(
    request: SearchRequest,
    processed,
    region,
    groups: list[SearchGroup],
    started: float,
) -> SearchResponse:
    took_ms = int((time.perf_counter() - started) * 1000)
    return SearchResponse(
        query=SearchQuery(
            original=processed.original,
            corrected=processed.corrected,
            region=region.id,
            region_name=region.name,
            synonyms_used=processed.synonyms,
            took_ms=took_ms,
        ),
        summary=_build_summary(groups),
        groups=groups,
    )


async def run_search(request: SearchRequest) -> SearchResponse:
    """Synchronous-style search (all sources). Used by background task."""
    started = time.perf_counter()
    processed = await process_query(request.query)
    region = resolve_region(request.region)
    search_request = SearchRequest(query=processed.corrected, region=region.id)
    groups_by_source: dict[str, SearchGroup] = {}
    enabled = _enabled_sources()
    logger.info("search_enabled_sources=%s", ",".join(_active_source_order()))

    async def _run_one(source: str, scraper: Any, coro: Coroutine[Any, Any, list[Product]]) -> None:
        products, error, status = await _safe_search(scraper, coro)
        if source == "other" and not products and not error:
            error = get_last_error()
            if error:
                status = "empty_with_diagnostics"
        groups_by_source[source] = _build_group(source, products, error, status)

    tasks: list[Coroutine[Any, Any, None]] = []
    if "wildberries" in enabled:
        tasks.append(_run_one("wildberries", wb.scraper, wb.scraper.search(search_request)))
    if "yandex_market" in enabled:
        tasks.append(
            _run_one(
                "yandex_market",
                yandex_market.scraper,
                yandex_market.scraper.search(search_request),
            )
        )
    if "other" in enabled:
        tasks.append(
            _run_one(
                "other",
                None,
                search_other_sources(search_request, original_query=processed.original),
            )
        )
    if tasks:
        await asyncio.gather(*tasks)
    if "ozon" in enabled:
        await _run_one("ozon", ozon.scraper, ozon.scraper.search(search_request))

    ordered = [groups_by_source[s] for s in _active_source_order() if s in groups_by_source]
    return _build_response(request, processed, region, ordered, started)


async def run_search_task(task_id: str, request: SearchRequest) -> None:
    """Background search with incremental progress for polling."""
    await search_task_store.set_running(task_id, message="Запуск поиска…")
    started = time.perf_counter()

    try:
        processed = await process_query(request.query)
        region = resolve_region(request.region)
        search_request = SearchRequest(query=processed.corrected, region=region.id)
        groups_by_source: dict[str, SearchGroup] = {}
        enabled = _enabled_sources()
        logger.info("search_enabled_sources=%s", ",".join(_active_source_order()))

        async def _run_and_publish(source: str, scraper, coro, message: str) -> None:
            await search_task_store.update_progress(task_id, message=message)
            products, error, status = await _safe_search(scraper, coro)
            if source == "other" and not products and not error:
                error = get_last_error()
                if error:
                    status = "empty_with_diagnostics"
            groups_by_source[source] = _build_group(source, products, error, status)
            partial = [
                groups_by_source[s]
                for s in _active_source_order()
                if s in groups_by_source
            ]
            await search_task_store.update_progress(
                task_id,
                message=f"Готово: {SOURCE_DISPLAY_NAMES[source]}",
                groups=partial,
            )

        parallel: list[Coroutine[Any, Any, None]] = []
        if "wildberries" in enabled:
            parallel.append(
                _run_and_publish(
                    "wildberries",
                    wb.scraper,
                    wb.scraper.search(search_request),
                    "Wildberries…",
                )
            )
        if "yandex_market" in enabled:
            parallel.append(
                _run_and_publish(
                    "yandex_market",
                    yandex_market.scraper,
                    yandex_market.scraper.search(search_request),
                    "Яндекс Маркет…",
                )
            )
        if "other" in enabled:
            parallel.append(
                _run_and_publish(
                    "other",
                    None,
                    search_other_sources(search_request, original_query=processed.original),
                    "Другие источники…",
                )
            )
        if parallel:
            await asyncio.gather(*parallel)
        if "ozon" in enabled:
            await _run_and_publish(
                "ozon",
                ozon.scraper,
                ozon.scraper.search(search_request),
                "Ozon: браузер проходит WAF (до 35 с)…",
            )

        ordered = [groups_by_source[s] for s in _active_source_order() if s in groups_by_source]
        response = _build_response(request, processed, region, ordered, started)
        await search_task_store.complete(task_id, response)
    except Exception as exc:
        logger.exception("Search task %s failed", task_id)
        await search_task_store.fail(task_id, f"{type(exc).__name__}: {exc}")


def spawn_search_task(task_id: str, request: SearchRequest) -> asyncio.Task[None]:
    return asyncio.create_task(run_search_task(task_id, request), name=f"search-{task_id[:8]}")

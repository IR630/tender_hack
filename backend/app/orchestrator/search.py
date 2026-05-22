import asyncio
import time

from app.core.models import (
    Product,
    SearchGroup,
    SearchQuery,
    SearchRequest,
    SearchResponse,
    SearchSummary,
)
from app.core.regions import resolve_region
from app.query.processor import process_query
from app.scrapers import ozon, wb, yandex_market
from app.sources.other.search import search_other_sources

SOURCE_DISPLAY_NAMES = {
    "wildberries": "Wildberries",
    "ozon": "Ozon",
    "yandex_market": "Яндекс Маркет",
    "other": "Другие источники",
}


async def _safe_search(coro) -> list[Product]:
    try:
        return await coro
    except Exception:
        return []


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


def _build_group(source: str, products: list[Product]) -> SearchGroup:
    min_price = min((product.price for product in products), default=None)
    domains = sorted({product.source_domain for product in products if product.source_domain})
    return SearchGroup(
        source=source,  # type: ignore[arg-type]
        display_name=SOURCE_DISPLAY_NAMES[source],
        count=len(products),
        min_price=min_price,
        domains=domains,
        products=products,
    )


async def run_search(request: SearchRequest) -> SearchResponse:
    started = time.perf_counter()
    processed = process_query(request.query)
    region = resolve_region(request.region)

    search_request = SearchRequest(query=processed.corrected, region=region.id)

    results = await asyncio.gather(
        _safe_search(wb.scraper.search(search_request)),
        _safe_search(yandex_market.scraper.search(search_request)),
        _safe_search(ozon.scraper.search(search_request)),
        _safe_search(search_other_sources(search_request)),
    )

    groups = [
        _build_group("wildberries", results[0]),
        _build_group("yandex_market", results[1]),
        _build_group("ozon", results[2]),
        _build_group("other", results[3]),
    ]

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

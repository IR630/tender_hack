from __future__ import annotations

import asyncio
import logging

from app.core.cache import cache_get, cache_set
from app.core.models import Product, SearchRequest
from app.core.regions import resolve_region
from other_public_scraper.config import settings as other_settings
from other_public_scraper.diagnostics import get_diagnostics
from other_public_scraper.scraper import search_other

logger = logging.getLogger(__name__)

settings = other_settings
_last_error: str | None = None


def get_last_error() -> str | None:
    return _last_error


def _cache_key(region: str, query: str) -> str:
    return f"other:search:{region}:{query.strip().lower()}"


def _to_product(item) -> Product:
    return Product(
        source="other",
        source_domain=item.source_domain,
        title=item.title,
        description=item.description,
        price=int(item.price_rub) * 100,
        image_url=item.image_url or "",
        product_url=item.product_url,
        characteristics=dict(item.characteristics),
        relevance_score=float(item.relevance_score),
        confidence=float(item.confidence),
    )


async def _run_search(query: str, region: str, *, on_partial=None) -> list[Product]:
    if other_settings.other_cache_enabled:
        cached = cache_get(_cache_key(region, query))
        if cached is not None:
            logger.info(
                "other_cache_hit query=%r region=%s count=%d",
                query,
                region,
                len(cached),
            )
            return [Product.model_validate(item) for item in cached]
        logger.info("other_cache_miss query=%r region=%s", query, region)

    raw_on_partial = None
    if on_partial:
        async def raw_on_partial(raw_items) -> None:
            try:
                await on_partial([_to_product(item) for item in raw_items])
            except Exception:
                pass

    search_coro = (
        search_other(query, region, on_partial=raw_on_partial)
        if raw_on_partial
        else search_other(query, region)
    )
    raw = await asyncio.wait_for(
        search_coro,
        timeout=other_settings.other_search_timeout_seconds,
    )
    products = [_to_product(item) for item in raw]
    logger.info("other_integration query=%r raw_results=%d", query, len(products))
    if other_settings.other_cache_enabled and products:
        cache_set(
            _cache_key(region, query),
            [p.model_dump(mode="json") for p in products],
        )
    elif other_settings.other_cache_enabled and not products:
        logger.info("other_cache_skip_empty query=%r — пустой результат не кэшируется", query)
    return products


async def search_other_sources(
    request: SearchRequest,
    *,
    original_query: str | None = None,
    on_partial=None,
) -> list[Product]:
    global _last_error
    _last_error = None
    _ = resolve_region(request.region)
    original = (original_query or request.query).strip()
    corrected = request.query.strip()
    attempts: list[str] = []
    for candidate in (original, corrected):
        if candidate and candidate not in attempts:
            attempts.append(candidate)

    last_diag_message: str | None = None
    for query in attempts:
        try:
            products = await _run_search(query, request.region, on_partial=on_partial)
            if products:
                _last_error = None
                return products
            diag = get_diagnostics()
            if diag is not None:
                last_diag_message = diag.format_user_message()
        except TimeoutError:
            logger.warning("other source timeout query=%r", query)
            last_diag_message = f"Другие источники: таймаут поиска по запросу {query!r}"
        except Exception as exc:
            logger.exception("other source failed query=%r", query)
            last_diag_message = f"Другие источники: {type(exc).__name__}: {exc}"

    _last_error = last_diag_message or (
        "Другие источники: 0 товаров — не удалось получить данные из сети"
    )
    return []

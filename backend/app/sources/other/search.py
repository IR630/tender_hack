from __future__ import annotations

import asyncio
import logging

from app.core.cache import cache_get, cache_set
from app.core.config import settings
from app.core.models import Product, SearchRequest
from app.core.regions import resolve_region
from other_public_scraper.scraper import search_other

logger = logging.getLogger(__name__)


def _cache_key(region: str, query: str) -> str:
    return f"other:search:{region}:{query.strip().lower()}"


def _to_product(item) -> Product:
    return Product(
        source="other",
        source_domain=item.source_domain,
        title=item.title,
        description=item.description,
        price=int(item.price_rub) * 100,
        image_url=item.image_url,
        product_url=item.product_url,
        characteristics=dict(item.characteristics),
        relevance_score=float(item.relevance_score),
        confidence=float(item.confidence),
    )


async def _run_search(query: str, region: str) -> list[Product]:
    if settings.other_cache_enabled:
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

    raw = await asyncio.wait_for(
        search_other(query, region),
        timeout=settings.other_search_timeout_seconds,
    )
    products = [_to_product(item) for item in raw]
    logger.info("other_integration query=%r raw_results=%d", query, len(products))
    if settings.other_cache_enabled and products:
        cache_set(
            _cache_key(region, query),
            [p.model_dump(mode="json") for p in products],
        )
    elif settings.other_cache_enabled and not products:
        logger.info("other_cache_skip_empty query=%r — пустой результат не кэшируется", query)
    return products


async def search_other_sources(
    request: SearchRequest,
    *,
    original_query: str | None = None,
) -> list[Product]:
    _ = resolve_region(request.region)
    original = (original_query or request.query).strip()
    corrected = request.query.strip()
    attempts: list[str] = []
    for candidate in (original, corrected):
        if candidate and candidate not in attempts:
            attempts.append(candidate)

    for query in attempts:
        try:
            products = await _run_search(query, request.region)
            if products:
                return products
        except TimeoutError:
            logger.warning("other source timeout query=%r", query)
        except Exception:
            logger.exception("other source failed query=%r", query)
    return []

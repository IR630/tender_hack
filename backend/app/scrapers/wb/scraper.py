from __future__ import annotations

import asyncio
import logging

from app.core.cache import cache_get, cache_set
from app.core.config import settings
from app.core.models import Product, SearchRequest
from app.core.regions import Region, resolve_region
from app.scrapers.base import BaseScraper
from app.scrapers.wb.assemble import assemble_products
from app.scrapers.wb.images import resolve_product_images
from app.scrapers.wb.circuit import circuit_is_open
from app.scrapers.wb.logging_utils import log_wb_request
from app.scrapers.wb.metrics import wb_metrics
from app.scrapers.wb.models import RhythmState
from app.scrapers.wb.rhythm import wait_before_request
from app.scrapers.wb.session import wb_session

logger = logging.getLogger(__name__)

_rhythm_state = RhythmState()


def _cache_key(region: str, query: str) -> str:
    return f"wb:search:{region}:{query.strip().lower()}"


async def _load_cached_products(region: str, query: str) -> list[Product] | None:
    if not settings.wb_cache_enabled:
        return None
    cached = await asyncio.to_thread(cache_get, _cache_key(region, query))
    if cached is None:
        return None
    logger.info("WB cache hit for query=%r region=%r", query, region)
    await wb_metrics.record(
        success=True,
        latency_ms=0.0,
        status_code=200,
        cache_hit=True,
    )
    log_wb_request(
        phase="search",
        user_id=wb_session.user_id,
        endpoint="cache",
        status=200,
        latency_ms=0.0,
        retry_count=0,
        cache_hit=True,
        impersonate_profile=wb_session.preset.impersonate_profile,
        query=query,
    )
    return [Product.model_validate(item) for item in cached]


async def _store_cached_products(region: str, query: str, products: list[Product]) -> None:
    if not settings.wb_cache_enabled or not products:
        return
    payload = [product.model_dump(mode="json") for product in products]
    await asyncio.to_thread(cache_set, _cache_key(region, query), payload)


class WBParser:
    """Wildberries search parser (phase 1: session warmup + PRIMARY fetch)."""

    async def search(
        self,
        query: str,
        region: Region,
        *,
        on_partial=None,
    ) -> tuple[list[Product], str | None]:
        query = query.strip()
        if not query:
            return [], None

        cached = await _load_cached_products(region.id, query)
        if cached is not None:
            return cached, None

        if circuit_is_open():
            return [], (
                "Wildberries временно недоступен (слишком много блокировок). "
                f"Повторите через {int(settings.wb_circuit_breaker_seconds // 60)} мин."
            )

        params = {
            "query": query,
            "resultset": "catalog",
            "dest": region.wb_dest,
            "curr": "rub",
            "lang": "ru",
            "appType": 1,
            "page": 1,
        }

        await wait_before_request(_rhythm_state)
        attempt = await wb_session.fetch_search(params)
        if attempt.error:
            logger.warning("WB parser failed for query=%r: %s", query, attempt.error)
            return [], attempt.error

        assembled = assemble_products(attempt.products)
        if not assembled:
            return [], "Wildberries вернул товары, но ни один не прошёл фильтрацию (цена/поля)"

        fast_batch = await resolve_product_images(assembled[:5])
        if on_partial and fast_batch:
            try:
                await on_partial(fast_batch)
            except Exception:
                pass

        rest_batch = await resolve_product_images(assembled[5:15])
        products = fast_batch + rest_batch

        await _store_cached_products(region.id, query, products)
        logger.info(
            "WB parser funnel for %r: %d raw -> %d fast + %d rest = %d total",
            query,
            len(attempt.products),
            len(fast_batch),
            len(rest_batch),
            len(products),
        )
        return products, None


wb_parser = WBParser()


class WildberriesScraper(BaseScraper):
    source = "wildberries"

    async def search(self, request: SearchRequest, *, on_partial=None) -> list[Product]:
        self.clear_error()
        region = resolve_region(request.region)
        products, error = await wb_parser.search(request.query, region, on_partial=on_partial)
        if error:
            self.set_error(error)
            return []
        return products


scraper = WildberriesScraper()

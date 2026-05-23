from __future__ import annotations

import asyncio
import time
import uuid

from ozon_public_scraper.logging_config import (
    bind_correlation,
    clear_correlation,
    get_logger,
    setup_logging,
)
from ozon_public_scraper.models import ProductResult, ScraperError, ScraperErrorType, SearchMetrics
from ozon_public_scraper.pipelines.og_fetcher import fetch_product_og
from ozon_public_scraper.pipelines.searxng import search_ozon_urls
from ozon_public_scraper.storage.meili import search_products

logger = get_logger("ozon_public.scraper")


class OzonPublicScraper:
    def __init__(self, region: str = "spb") -> None:
        setup_logging()
        self.region = region

    async def search(
        self,
        query: str,
        region: str | None = None,
        limit: int = 10,
    ) -> list[ProductResult]:
        region = region or self.region
        correlation_id = str(uuid.uuid4())
        bind_correlation(correlation_id)
        t0 = time.perf_counter()
        metrics = SearchMetrics()

        logger.info(
            "user_query_received",
            context={"query": query, "region": region, "limit": limit},
        )

        try:
            meili_task = search_products(query, limit=limit * 2)
            searxng_task = search_ozon_urls(query, limit=limit * 2)
            meili_result, searxng_urls = await asyncio.gather(meili_task, searxng_task)
            meili_urls = meili_result[0]

            metrics.meili_count = len(meili_urls)
            metrics.searxng_count = len(searxng_urls)

            merged: dict[str, tuple[str, str]] = {}  # id -> (url, source)
            for p in meili_urls:
                merged[p.numeric_id] = (str(p.url), "meilisearch")
            for p in searxng_urls:
                if p.numeric_id not in merged:
                    merged[p.numeric_id] = (str(p.url), "searxng")

            if not merged:
                raise ScraperError(
                    "No product URLs from Meilisearch or SearXNG",
                    ScraperErrorType.ALL_SOURCES_FAILED,
                )

            urls_to_fetch = list(merged.items())[:limit]
            results: list[ProductResult] = []

            async def _fetch_one(numeric_id: str, url: str, source: str) -> ProductResult | None:
                return await fetch_product_og(url, numeric_id, source=source)

            fetched = await asyncio.gather(
                *[_fetch_one(nid, url, src) for nid, (url, src) in urls_to_fetch]
            )

            for item in fetched:
                if item is None:
                    continue
                if item.source == "cache":
                    metrics.cache_count += 1
                if item.incomplete:
                    metrics.items_incomplete += 1
                results.append(item)

            total_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "query_completed",
                context={
                    "total_latency_ms": total_ms,
                    "items_returned": len(results),
                    "items_incomplete": metrics.items_incomplete,
                    "sources_used": {
                        "meili": metrics.meili_count,
                        "searxng": metrics.searxng_count,
                        "cache": metrics.cache_count,
                    },
                },
            )
            return results

        except ScraperError as exc:
            logger.critical(
                "query_failed",
                context={
                    "error_type": exc.error_type.value,
                    "last_error": exc.message,
                    "attempts": 1,
                },
            )
            raise
        finally:
            clear_correlation()

from __future__ import annotations

import asyncio

from tenacity import retry, stop_after_attempt, wait_exponential

from ozon_public_scraper.config import settings
from ozon_public_scraper.logging_config import get_logger
from ozon_public_scraper.models import ProductResult, RawOgData
from ozon_public_scraper.parsers.og_extractor import extract_og
from ozon_public_scraper.storage.cache import (
    blocked_url_key,
    cache_get,
    cache_set,
    og_cache_key,
)
from ozon_public_scraper.storage.meili import delete_product
from ozon_public_scraper.transport import fetch_url

logger = get_logger("ozon_public.pipelines.og_fetcher")


def _og_to_product(raw: RawOgData, *, url: str, source: str) -> ProductResult | None:
    if not raw.title:
        return None
    incomplete = raw.price_rub is None
    return ProductResult(
        title=raw.title,
        price_rub=raw.price_rub,
        image_url=raw.image_url,
        product_url=raw.canonical_url or url,
        description=raw.description,
        characteristics={
            **({"availability": raw.availability} if raw.availability else {}),
            **({"currency": raw.currency} if raw.currency else {}),
        },
        incomplete=incomplete,
        source=source,
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
async def _fetch_page(url: str, attempt: int) -> tuple[int, str]:
    accept_langs = ["ru-RU,ru;q=0.9", "ru,en;q=0.8", "en-US,en;q=0.5"]
    lang = accept_langs[min(attempt - 1, len(accept_langs) - 1)]
    result = await fetch_url(
        url,
        apply_ozon_limit=True,
    )
    return result.status_code, result.body.decode("utf-8", errors="replace")


async def fetch_product_og(
    url: str,
    numeric_id: str,
    *,
    source: str = "meilisearch",
) -> ProductResult | None:
    if await cache_get(blocked_url_key(numeric_id)):
        logger.info("og_fetch_skipped_blocked", context={"url": url, "numeric_id": numeric_id})
        return None

    cache_key = og_cache_key(numeric_id)
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("cache_hit_og", context={"cache_key": cache_key})
        return ProductResult.model_validate({**cached, "source": "cache"})

    logger.info("cache_miss_og", context={"cache_key": cache_key})

    import time

    for attempt in range(1, 4):
        logger.info("og_fetch_started", context={"url": url, "attempt": attempt})
        t0 = time.perf_counter()
        try:
            status, html = await _fetch_page(url, attempt)
        except Exception as exc:
            logger.error("og_fetch_error", context={"url": url, "error": str(exc)})
            return None

        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "og_fetch_completed",
            context={
                "url": url,
                "status_code": status,
                "latency_ms": latency_ms,
                "bytes": len(html.encode()),
                "fields_extracted": [],
                "fields_missing": [],
            },
        )

        if status == 404:
            logger.info("product_url_invalid", context={"url": url, "removed_from_index": True})
            await delete_product(numeric_id)
            return None

        if status == 403:
            logger.warning("ozon_blocked_og_fetch", context={"url": url, "attempt": attempt})
            if attempt < 3:
                await asyncio.sleep(5)
                continue
            await cache_set(blocked_url_key(numeric_id), {"blocked": True}, settings.ozon_blocked_url_ttl)
            return None

        if status >= 500:
            raise RuntimeError(f"server error {status}")

        if status != 200:
            return None

        raw = extract_og(html, url=url)
        product = _og_to_product(raw, url=url, source=source)
        if product is None:
            return None

        logger.info(
            "og_fetch_completed",
            context={
                "url": url,
                "status_code": status,
                "latency_ms": latency_ms,
                "bytes": len(html.encode()),
                "fields_extracted": raw.fields_extracted,
                "fields_missing": raw.fields_missing,
            },
        )

        ttl = settings.ozon_og_incomplete_cache_ttl if product.incomplete else settings.ozon_og_cache_ttl
        await cache_set(cache_key, product.model_dump(mode="json"), ttl)
        return product

    return None

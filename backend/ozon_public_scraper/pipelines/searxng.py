from __future__ import annotations

import re
from urllib.parse import quote_plus

import httpx

from ozon_public_scraper.config import settings
from ozon_public_scraper.logging_config import get_logger
from ozon_public_scraper.models import ProductUrl
from ozon_public_scraper.pipelines.sitemap import parse_product_url
from ozon_public_scraper.storage.cache import cache_get, cache_set, searxng_cache_key

logger = get_logger("ozon_public.pipelines.searxng")

PRODUCT_LINK_RE = re.compile(r"https?://(?:www\.)?ozon\.ru/product/[^\s\"']+")


async def search_ozon_urls(query: str, *, limit: int = 20) -> list[ProductUrl]:
    cache_key = searxng_cache_key(query)
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("cache_hit_searxng", context={"cache_key": cache_key})
        return [ProductUrl.model_validate(item) for item in cached]

    logger.info("cache_miss_searxng", context={"cache_key": cache_key})

    q = f"site:ozon.ru {query}"
    url = f"{settings.searxng_url.rstrip('/')}/search"
    params = {"q": q, "format": "json", "safesearch": "0"}

    import time

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=settings.ozon_request_timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        logger.warning("searxng_query_failed", context={"query": query, "error": str(exc)})
        return []

    latency_ms = int((time.perf_counter() - t0) * 1000)
    results = payload.get("results") or []
    products: list[ProductUrl] = []
    seen: set[str] = set()

    for item in results:
        if not isinstance(item, dict):
            continue
        link = item.get("url") or ""
        if "ozon.ru/product/" not in link:
            continue
        product = parse_product_url(link)
        if product and product.numeric_id not in seen:
            seen.add(product.numeric_id)
            products.append(product)

    logger.info(
        "searxng_query",
        context={
            "query": query,
            "engine": "searxng",
            "results_count": len(products),
            "latency_ms": latency_ms,
        },
    )

    if len(products) < 3:
        logger.warning(
            "searxng_low_yield",
            context={"query": query, "ozon_urls_count": len(products)},
        )

    if products:
        await cache_set(
            cache_key,
            [p.model_dump(mode="json") for p in products],
            settings.ozon_searxng_cache_ttl,
        )

    return products[:limit]

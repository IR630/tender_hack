"""Live web search: SearXNG first, Bing fallback."""

from __future__ import annotations

import logging

from other_public_scraper.config import settings
from other_public_scraper.models import UrlCandidate
from other_public_scraper.pipelines.bing_search import search_bing_urls
from other_public_scraper.pipelines.searxng import search_other_urls

logger = logging.getLogger(__name__)


def _merge_live(*groups: list[UrlCandidate]) -> list[UrlCandidate]:
    merged: dict[str, UrlCandidate] = {}
    for group in groups:
        for item in group:
            key = item.url.split("#")[0]
            if key not in merged:
                merged[key] = item
    return list(merged.values())


async def search_live_urls(query: str, *, limit: int | None = None) -> list[UrlCandidate]:
    """Query the public web for product/store URLs (no Meili reads)."""
    limit = limit or settings.other_max_searxng_urls

    if settings.other_bing_primary_enabled:
        bing_hits = await search_bing_urls(query, limit=limit)
        if bing_hits:
            logger.info("other_live_search query=%r provider=bing count=%d", query, len(bing_hits))
            return bing_hits

    searxng_hits = await search_other_urls(query, limit=limit)
    if searxng_hits:
        logger.info("other_live_search query=%r provider=searxng count=%d", query, len(searxng_hits))
        return searxng_hits

    if settings.other_bing_fallback_enabled and not settings.other_bing_primary_enabled:
        logger.info("other_live_search query=%r searxng=0 trying_bing", query)
        bing_hits = await search_bing_urls(query, limit=limit)
        if bing_hits:
            logger.info("other_live_search query=%r provider=bing count=%d", query, len(bing_hits))
            return bing_hits

    logger.warning("other_live_search query=%r all_providers=0", query)
    return []

"""Live web search: Yahoo + SearXNG + DDG in parallel, Bing optional fallback."""

from __future__ import annotations

import asyncio
import logging

from other_public_scraper.config import settings
from other_public_scraper.diagnostics import active_diagnostics
from other_public_scraper.models import UrlCandidate
from other_public_scraper.pipelines.bing_search import search_bing_urls
from other_public_scraper.pipelines.ddg_search import search_ddg_urls
from other_public_scraper.pipelines.searxng import search_other_urls
from other_public_scraper.pipelines.yahoo_search import search_yahoo_urls
from other_public_scraper.query_variants import search_query_variants
from other_public_scraper.url_heuristics import (
    filter_and_sort_candidates,
    looks_like_listing_url,
    url_quality_score,
)

logger = logging.getLogger(__name__)


def _merge_live(*groups: list[UrlCandidate]) -> list[UrlCandidate]:
    merged: dict[str, UrlCandidate] = {}
    for group in groups:
        for item in group:
            key = item.url.split("#")[0]
            if key not in merged:
                merged[key] = item
    return list(merged.values())


def _select_live_candidates(candidates: list[UrlCandidate], *, limit: int) -> list[UrlCandidate]:
    """Keep concrete product URLs plus listing seeds for the catalog expander."""
    if not candidates:
        return []
    product_hits = [
        item
        for item in filter_and_sort_candidates(candidates)
        if url_quality_score(item.url) >= 0
    ]
    listing_seeds = [item for item in candidates if looks_like_listing_url(item.url)]
    return _merge_live(product_hits, listing_seeds)[:limit]


async def _run_provider(
    name: str, task: asyncio.Task[list[UrlCandidate]]
) -> tuple[str, list[UrlCandidate]]:
    try:
        hits = await task
    except Exception as exc:
        logger.warning("other_live provider=%s failed: %s", name, exc)
        return name, []
    return name, hits


async def search_live_urls(
    query: str, *, limit: int | None = None, allow_fallbacks: bool = True
) -> list[UrlCandidate]:
    """Discover product URLs via generic web search (no site-specific endpoints)."""
    limit = limit or settings.other_max_searxng_urls

    primary_tasks: list[tuple[str, asyncio.Task[list[UrlCandidate]]]] = []
    if settings.other_yahoo_enabled:
        primary_tasks.append(("yahoo", asyncio.create_task(search_yahoo_urls(query, limit=limit))))
    primary_tasks.append(("searxng", asyncio.create_task(search_other_urls(query, limit=limit))))
    if settings.other_ddg_enabled:
        primary_tasks.append(("ddg", asyncio.create_task(search_ddg_urls(query, limit=limit))))

    source_counts: dict[str, int] = {}
    groups: list[list[UrlCandidate]] = []
    providers_ok: list[str] = []

    for name, hits in await asyncio.gather(
        *[_run_provider(name, task) for name, task in primary_tasks]
    ):
        source_counts[name] = len(hits)
        if hits:
            providers_ok.append(name)
            groups.append(hits)

    merged_raw = _merge_live(*groups) if groups else []
    merged = _select_live_candidates(merged_raw, limit=limit)
    if merged:
        diag = active_diagnostics()
        diag.live_provider = "+".join(providers_ok)
        diag.live_urls = len(merged)
        diag.live_sample = [item.url[:90] for item in merged[:5]]
        logger.info(
            "other_live_search query=%r providers=%s count=%d filtered_from=%d",
            query,
            diag.live_provider,
            len(merged),
            len(merged_raw),
        )
        return merged

    if not allow_fallbacks:
        return []

    if settings.other_bing_fallback_enabled:
        _, bing_hits = await _run_provider(
            "bing",
            asyncio.create_task(search_bing_urls(query, limit=limit)),
        )
        source_counts["bing"] = len(bing_hits)
        bing_hits = _select_live_candidates(bing_hits, limit=limit)
        if bing_hits:
            diag = active_diagnostics()
            diag.live_provider = "bing"
            diag.live_urls = len(bing_hits)
            diag.live_sample = [item.url[:90] for item in bing_hits[:5]]
            logger.info(
                "other_live_search query=%r fallback=bing count=%d",
                query,
                len(bing_hits),
            )
            return bing_hits[:limit]

    logger.warning("other_live_search query=%r all_providers=0 sources=%s", query, source_counts)
    return []


async def search_live_urls_expanded(
    query: str,
    *,
    limit: int | None = None,
    category: str = "unknown",
) -> list[UrlCandidate]:
    """Run live search across query variants (search-only discovery)."""
    _ = category
    limit = limit or settings.other_max_searxng_urls
    variants = search_query_variants(query)
    variant_tasks = [
        search_live_urls(variant, limit=limit, allow_fallbacks=True) for variant in variants
    ]
    groups = await asyncio.gather(*variant_tasks)
    merged = _merge_live(*groups)
    return _select_live_candidates(merged, limit=limit)

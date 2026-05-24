"""Live web search: Yahoo + SearXNG + DDG in parallel, Bing optional fallback."""

from __future__ import annotations

import asyncio
import logging
import re

from other_public_scraper.config import settings
from other_public_scraper.diagnostics import active_diagnostics
from other_public_scraper.grocery_seeds import is_grocery_query
from other_public_scraper.models import UrlCandidate
from other_public_scraper.pipelines.bing_search import search_bing_urls
from other_public_scraper.pipelines.ddg_search import search_ddg_urls
from other_public_scraper.pipelines.searxng import search_other_urls
from other_public_scraper.pipelines.sitemap_search import search_sitemap_urls
from other_public_scraper.pipelines.yahoo_search import search_yahoo_urls
from other_public_scraper.query_variants import search_query_variants
from other_public_scraper.url_heuristics import (
    filter_and_sort_candidates,
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
    merged = filter_and_sort_candidates(merged_raw)[:limit] if merged_raw else []
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

    _, sitemap_hits = await _run_provider(
        "sitemap",
        asyncio.create_task(search_sitemap_urls(query, limit=limit)),
    )
    source_counts["sitemap"] = len(sitemap_hits)
    if sitemap_hits:
        diag = active_diagnostics()
        diag.live_provider = "sitemap"
        diag.live_urls = len(sitemap_hits)
        diag.live_sample = [item.url[:90] for item in sitemap_hits[:5]]
        logger.info(
            "other_live_search query=%r fallback=sitemap count=%d",
            query,
            len(sitemap_hits),
        )
        return sitemap_hits[:limit]

    logger.warning("other_live_search query=%r all_providers=0 sources=%s", query, source_counts)
    return []


async def _search_ddg_supplement(query: str, *, limit: int) -> list[UrlCandidate]:
    if not settings.other_ddg_enabled:
        return []
    per_query = max(5, limit // 3)
    variants = search_query_variants(query)
    latin = next(
        (v for v in variants if re.search(r"iphone\s+\d", v, re.IGNORECASE)),
        query,
    )
    tasks = [
        search_ddg_urls(f"{latin} купить", limit=per_query),
        search_ddg_urls(f"{latin} site:cmstore.ru", limit=4),
        search_ddg_urls(f"{latin} site:re-store.ru", limit=4),
        search_ddg_urls(f"{latin} site:shop.mts.ru", limit=4),
    ]
    groups = await asyncio.gather(*tasks, return_exceptions=True)
    merged: list[UrlCandidate] = []
    for group in groups:
        if isinstance(group, list):
            merged.extend(group)
    return merged


async def search_live_urls_expanded(
    query: str,
    *,
    limit: int | None = None,
    category: str = "unknown",
) -> list[UrlCandidate]:
    """Run live search across query variants and orgtech shop supplements."""
    limit = limit or settings.other_max_searxng_urls
    variants = search_query_variants(query)
    variant_tasks = [
        search_live_urls(variant, limit=limit, allow_fallbacks=False) for variant in variants[:3]
    ]
    groups = await asyncio.gather(*variant_tasks)
    merged = _merge_live(*groups)
    if category == "orgtech":
        supplemental = await _search_ddg_supplement(query, limit=limit)
        merged = _merge_live(merged, supplemental)
    merged = filter_and_sort_candidates(merged)
    merged = [item for item in merged if url_quality_score(item.url) >= 0][:limit]
    return merged

"""Live web search: Yahoo + SearXNG + DDG in parallel, Bing optional fallback."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from other_public_scraper.config import settings
from other_public_scraper.debug_log import agent_log
from other_public_scraper.diagnostics import active_diagnostics
from other_public_scraper.models import UrlCandidate
from other_public_scraper.url_heuristics import filter_and_sort_candidates, is_rejected_url, url_quality_score
from other_public_scraper.pipelines.bing_search import search_bing_urls
from other_public_scraper.pipelines.ddg_search import search_ddg_urls
from other_public_scraper.pipelines.searxng import search_other_urls
from other_public_scraper.pipelines.sitemap_search import search_sitemap_urls
from other_public_scraper.pipelines.yahoo_search import search_yahoo_urls

logger = logging.getLogger(__name__)

# #region agent log
_DEBUG_LOG_PATH = "/home/ir6/my/tender_hack/.cursor/debug-6c5798.log"
_DEBUG_SESSION = "6c5798"


def _debug_log(*, hypothesis_id: str, location: str, message: str, data: dict | None = None) -> None:
    entry = {
        "sessionId": _DEBUG_SESSION,
        "timestamp": int(time.time() * 1000),
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
    }
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


# #endregion


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
        _debug_log(
            hypothesis_id="H1",
            location="web_search.py:_run_provider",
            message="provider_failed",
            data={"provider": name, "error": repr(exc)},
        )
        return name, []
    return name, hits


async def search_live_urls(query: str, *, limit: int | None = None) -> list[UrlCandidate]:
    """Discover product URLs via generic web search (no site-specific endpoints)."""
    limit = limit or settings.other_max_searxng_urls
    _debug_log(
        hypothesis_id="H1",
        location="web_search.py:search_live_urls",
        message="discovery_start",
        data={"query": query, "limit": limit},
    )

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
        _debug_log(
            hypothesis_id="H1",
            location="web_search.py:search_live_urls",
            message="discovery_complete",
            data={
                "query": query,
                "source_counts": source_counts,
                "merged_count": len(merged),
                "raw_count": len(merged_raw),
                "providers": providers_ok,
                "sample_urls": [item.url[:90] for item in merged[:5]],
                "rejected_count": sum(1 for c in merged_raw if is_rejected_url(c.url)),
            },
        )
        agent_log(
            hypothesis_id="H1",
            location="web_search.py:search_live_urls",
            message="discovery_complete",
            data={
                "query": query,
                "source_counts": source_counts,
                "merged_count": len(merged),
                "providers": providers_ok,
            },
        )
        return merged

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
        _debug_log(
            hypothesis_id="H3",
            location="web_search.py:search_live_urls",
            message="discovery_sitemap_fallback",
            data={"query": query, "source_counts": source_counts, "merged_count": len(sitemap_hits)},
        )
        return sitemap_hits[:limit]

    logger.warning("other_live_search query=%r all_providers=0 sources=%s", query, source_counts)
    _debug_log(
        hypothesis_id="H1",
        location="web_search.py:search_live_urls",
        message="discovery_empty",
        data={"query": query, "source_counts": source_counts},
    )
    agent_log(
        hypothesis_id="H1",
        location="web_search.py:search_live_urls",
        message="discovery_empty",
        data={"query": query, "source_counts": source_counts, "merged_count": 0},
    )
    return []

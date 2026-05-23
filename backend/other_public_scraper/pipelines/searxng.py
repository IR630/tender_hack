from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

import httpx

from other_public_scraper.config import DOMAIN_BLACKLIST, settings
from other_public_scraper.debug_log import agent_log
from other_public_scraper.diagnostics import active_diagnostics
from other_public_scraper.models import UrlCandidate

logger = logging.getLogger(__name__)

_searxng_cache: dict[str, list[UrlCandidate]] = {}


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _is_blacklisted(url: str) -> bool:
    domain = _domain(url)
    return domain in DOMAIN_BLACKLIST or any(b in domain for b in DOMAIN_BLACKLIST)


async def search_other_urls(query: str, *, limit: int = 20) -> list[UrlCandidate]:
    cache_key = query.strip().lower()
    if cache_key in _searxng_cache:
        return _searxng_cache[cache_key][:limit]

    q = (
        f"{query} купить цена "
        f"-site:wildberries.ru -site:ozon.ru -site:market.yandex.ru "
        f"-site:gsmarena.com -site:nanoreview.net -site:apple.com"
    )
    url = f"{settings.searxng_url.rstrip('/')}/search"
    params = {"q": q, "format": "json", "safesearch": "0", "language": "ru-RU"}
    agent_log(
        hypothesis_id="H2",
        location="searxng.py:search_other_urls",
        message="searxng_query",
        data={"query": query, "searxng_q": q},
    )

    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=settings.other_request_timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        logger.warning("other searxng failed query=%r: %s", query, exc)
        return []

    results: list[UrlCandidate] = []
    seen: set[str] = set()
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        link = str(item.get("url") or "")
        if not link.startswith("http") or _is_blacklisted(link):
            continue
        domain = _domain(link)
        if link in seen:
            continue
        seen.add(link)
        results.append(
            UrlCandidate(
                url=link,
                domain=domain,
                title=str(item.get("title") or ""),
                snippet=str(item.get("content") or item.get("snippet") or ""),
                source="searxng",
            )
        )
        if len(results) >= limit:
            break

    logger.info(
        "other_searxng query=%r results=%d latency_ms=%d",
        query,
        len(results),
        int((time.perf_counter() - t0) * 1000),
    )
    if not results:
        unresponsive = payload.get("unresponsive_engines") or []
        diag = active_diagnostics()
        diag.searxng_unresponsive = [(str(a), str(b)) for a, b in unresponsive]
        if unresponsive:
            logger.warning(
                "other_searxng_zero query=%r unresponsive_engines=%s — "
                "SearXNG не смог опросить поисковики (timeout/CAPTCHA/VPN?)",
                query,
                unresponsive,
            )
        else:
            logger.warning(
                "other_searxng_zero query=%r — поисковики ответили, но URL не найдены",
                query,
            )
    else:
        _searxng_cache[cache_key] = results
    return results

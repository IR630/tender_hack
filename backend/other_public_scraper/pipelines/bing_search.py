"""Live web search via Bing HTML (fallback when SearXNG engines are down)."""

from __future__ import annotations

import asyncio
import asyncio
import logging
import re
import time
from urllib.parse import urlparse

from curl_cffi import requests as curl_requests
from selectolax.parser import HTMLParser

from other_public_scraper.config import DESKTOP_UA, DOMAIN_BLACKLIST, settings
from other_public_scraper.models import UrlCandidate

logger = logging.getLogger(__name__)

_CITE_RE = re.compile(r"^https?://[^\s›]+")


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _is_blacklisted(url: str) -> bool:
    domain = _domain(url)
    return domain in DOMAIN_BLACKLIST or any(b in domain for b in DOMAIN_BLACKLIST)


def _cite_to_url(cite: str) -> str | None:
    cite = cite.strip()
    if not cite:
        return None
    match = _CITE_RE.match(cite)
    if not match:
        return None
    base = match.group(0).rstrip("/")
    path_part = cite[len(match.group(0)) :].strip()
    if path_part.startswith("›"):
        path_part = path_part.lstrip("›").strip().replace(" › ", "/").replace("›", "/")
    if path_part and not path_part.startswith("/"):
        path_part = "/" + path_part.replace(" ", "/")
    url = base + path_part if path_part else base
    if not url.startswith("http"):
        return None
    return url


def _parse_bing_html(html: str, *, limit: int) -> list[UrlCandidate]:
    tree = HTMLParser(html)
    results: list[UrlCandidate] = []
    seen: set[str] = set()
    for li in tree.css("li.b_algo"):
        link = li.css_first("h2 a")
        cite_node = li.css_first("cite")
        if link is None or cite_node is None:
            continue
        url = _cite_to_url(cite_node.text(strip=True))
        if not url or not url.startswith("http") or _is_blacklisted(url):
            continue
        key = url.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        snippet_node = li.css_first(".b_caption p")
        results.append(
            UrlCandidate(
                url=url,
                domain=_domain(url),
                title=link.text(strip=True),
                snippet=snippet_node.text(strip=True) if snippet_node else "",
                source="bing",
            )
        )
        if len(results) >= limit:
            break
    return results


def _fetch_bing_sync(query: str, *, limit: int) -> list[UrlCandidate]:
    session = curl_requests.Session(impersonate="chrome120")
    response = session.get(
        "https://www.bing.com/search",
        params={"q": query, "setlang": "ru", "count": str(min(limit + 5, 30))},
        headers={"User-Agent": DESKTOP_UA, "Accept-Language": "ru-RU,ru;q=0.9"},
        timeout=settings.other_request_timeout,
    )
    response.raise_for_status()
    return _parse_bing_html(response.text, limit=limit)


async def search_bing_urls(query: str, *, limit: int = 20) -> list[UrlCandidate]:
    t0 = time.perf_counter()
    merged: dict[str, UrlCandidate] = {}

    def _merge(batch: list[UrlCandidate]) -> None:
        for item in batch:
            key = item.url.split("#")[0]
            if key not in merged:
                merged[key] = item

    primary_queries = [f"{query} купить", query]
    domains = [d.strip() for d in settings.other_precrawl_domains.split(",") if d.strip()]
    all_queries = primary_queries + [f"{query} site:{domains[0]}"] if domains else primary_queries

    for q in all_queries:
        if len(merged) >= limit:
            break
        try:
            batch = await asyncio.to_thread(_fetch_bing_sync, q, limit=limit)
            _merge(batch)
        except Exception as exc:
            logger.warning("other_bing failed query=%r: %s", q, exc)

    results = list(merged.values())[:limit]
    logger.info(
        "other_bing query=%r results=%d latency_ms=%d",
        query,
        len(results),
        int((time.perf_counter() - t0) * 1000),
    )
    if results:
        logger.info(
            "other_bing_sample query=%r urls=%s",
            query,
            [c.url[:70] for c in results[:5]],
        )
    return results

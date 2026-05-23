"""Generic web discovery via DuckDuckGo Lite HTML."""

from __future__ import annotations

import asyncio
import logging
import time
from urllib.parse import parse_qs, unquote, urlparse

from curl_cffi import requests as curl_requests
from selectolax.parser import HTMLParser

from other_public_scraper.config import DESKTOP_UA, DOMAIN_BLACKLIST, settings
from other_public_scraper.debug_log import agent_log
from other_public_scraper.models import UrlCandidate

logger = logging.getLogger(__name__)

DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _is_blacklisted(url: str) -> bool:
    domain = _domain(url)
    return domain in DOMAIN_BLACKLIST or any(b in domain for b in DOMAIN_BLACKLIST)


def _resolve_ddg_href(href: str) -> str | None:
    href = href.strip()
    if not href:
        return None
    if href.startswith("//"):
        href = f"https:{href}"
    if "duckduckgo.com/l/" in href and "uddg=" in href:
        parsed = urlparse(href)
        uddg = parse_qs(parsed.query).get("uddg", [""])[0]
        if uddg:
            href = unquote(uddg)
    if not href.startswith("http"):
        return None
    return href


def _parse_ddg_html(html: str, *, limit: int) -> list[UrlCandidate]:
    tree = HTMLParser(html)
    results: list[UrlCandidate] = []
    seen: set[str] = set()

    for link in tree.css("a.result-link"):
        href = link.attributes.get("href", "")
        url = _resolve_ddg_href(href)
        if not url or _is_blacklisted(url):
            continue
        key = url.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        title = link.text(strip=True)
        results.append(
            UrlCandidate(
                url=url,
                domain=_domain(url),
                title=title,
                snippet=title,
                source="ddg",
            )
        )
        if len(results) >= limit:
            break

    if results:
        return results

    for link in tree.css("a[href]"):
        href = link.attributes.get("href", "")
        url = _resolve_ddg_href(href)
        if not url or _is_blacklisted(url):
            continue
        key = url.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        title = link.text(strip=True)
        if len(title) < 5:
            continue
        results.append(
            UrlCandidate(
                url=url,
                domain=_domain(url),
                title=title,
                snippet=title,
                source="ddg",
            )
        )
        if len(results) >= limit:
            break
    return results


def _fetch_ddg_sync(query: str, *, limit: int) -> list[UrlCandidate]:
    session = curl_requests.Session(impersonate="chrome120")
    response = session.post(
        DDG_LITE_URL,
        data={"q": query, "kl": "ru-ru"},
        headers={
            "User-Agent": DESKTOP_UA,
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        },
        timeout=settings.other_ddg_timeout_seconds,
    )
    response.raise_for_status()
    return _parse_ddg_html(response.text, limit=limit)


async def search_ddg_urls(query: str, *, limit: int = 20) -> list[UrlCandidate]:
    search_query = f"{query} купить цена"
    agent_log(
        hypothesis_id="H2",
        location="ddg_search.py:search_ddg_urls",
        message="ddg_query",
        data={"query": query, "ddg_q": search_query},
    )
    t0 = time.perf_counter()
    try:
        results = await asyncio.to_thread(_fetch_ddg_sync, search_query, limit=limit)
    except Exception as exc:
        logger.warning("other_ddg failed query=%r: %r", search_query, exc)
        agent_log(
            hypothesis_id="H2",
            location="ddg_search.py:search_ddg_urls",
            message="ddg_failed",
            data={"query": query, "error": repr(exc)},
        )
        return []

    logger.info(
        "other_ddg query=%r results=%d latency_ms=%d",
        query,
        len(results),
        int((time.perf_counter() - t0) * 1000),
    )
    return results

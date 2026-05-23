"""Generic web discovery via Yahoo HTML search (works when DDG/Bing are blocked)."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from urllib.parse import urlparse

from curl_cffi import requests as curl_requests
from selectolax.parser import HTMLParser

from other_public_scraper.config import DESKTOP_UA, DOMAIN_BLACKLIST, settings
from other_public_scraper.diagnostics import active_diagnostics
from other_public_scraper.models import UrlCandidate

logger = logging.getLogger(__name__)

_CITE_URL_RE = re.compile(r"https?://[^\s›]+")
_TITLE_URL_RE = re.compile(r"https?://\S+")


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
    match = _CITE_URL_RE.search(cite)
    if not match:
        return None
    base = match.group(0).rstrip("/")
    if "›" not in cite:
        return base if base.startswith("http") else None
    path_part = cite.split("›", 1)[1]
    path_part = path_part.replace("›", "/").replace(" ", "").strip("/")
    if not path_part:
        return base
    return f"{base}/{path_part}"


def _clean_title(raw: str) -> str:
    title = _TITLE_URL_RE.sub("", raw)
    title = re.sub(r"\s+", " ", title).strip()
    return title or raw.strip()


def _is_consent_page(html: str) -> bool:
    lower = html.lower()
    if "datenschutzeinstellungen" in lower or "настройки конфиденциальности" in lower:
        return True
    if len(html) < 50_000 and "consent.yahoo.com" in lower:
        return True
    return False


def _parse_yahoo_html(html: str, *, limit: int) -> list[UrlCandidate]:
    tree = HTMLParser(html)
    results: list[UrlCandidate] = []
    seen: set[str] = set()

    for block in tree.css("div.algo"):
        title_node = block.css_first("h3.title a") or block.css_first("a")
        cite_node = block.css_first("span.fc-falcon") or block.css_first("cite")
        if title_node is None or cite_node is None:
            continue
        url = _cite_to_url(cite_node.text(strip=True))
        if not url or not url.startswith("http") or _is_blacklisted(url):
            continue
        key = url.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        snippet_node = block.css_first(".compText p") or block.css_first(".fc-falcon")
        results.append(
            UrlCandidate(
                url=url,
                domain=_domain(url),
                title=_clean_title(title_node.text(strip=True)),
                snippet=snippet_node.text(strip=True) if snippet_node else "",
                source="yahoo",
            )
        )
        if len(results) >= limit:
            break
    return results


def _fetch_yahoo_sync(query: str, *, limit: int) -> list[UrlCandidate]:
    session = curl_requests.Session(impersonate="chrome120")
    headers = {
        "User-Agent": DESKTOP_UA,
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml",
    }
    params = {
        "p": query,
        "n": str(min(limit + 5, 30)),
        "vm": "r",
        "fr": "yfp-t",
    }
    session.get("https://www.yahoo.com/", headers=headers, timeout=5)
    response = session.get(
        "https://search.yahoo.com/search",
        params=params,
        headers={**headers, "Referer": "https://www.yahoo.com/"},
        timeout=settings.other_yahoo_timeout_seconds,
    )
    response.raise_for_status()
    if _is_consent_page(response.text):
        return []
    return _parse_yahoo_html(response.text, limit=limit)


async def search_yahoo_urls(query: str, *, limit: int = 20) -> list[UrlCandidate]:
    t0 = time.perf_counter()
    diag = active_diagnostics()
    search_query = (
        f"{query} купить цена "
        f"-site:wildberries.ru -site:ozon.ru -site:market.yandex.ru "
        f"-site:gsmarena.com -site:apple.com"
    )

    results: list[UrlCandidate] = []
    last_error: str | None = None
    for attempt in range(2):
        try:
            results = await asyncio.to_thread(_fetch_yahoo_sync, search_query, limit=limit)
            if results:
                break
        except Exception as exc:
            last_error = str(exc)
            logger.warning("other_yahoo attempt=%d failed query=%r: %s", attempt + 1, search_query, exc)
            await asyncio.sleep(0.3)

    if last_error and not results:
        diag.yahoo_errors.append(f"{search_query!r}: {last_error}")

    logger.info(
        "other_yahoo query=%r results=%d latency_ms=%d",
        query,
        len(results),
        int((time.perf_counter() - t0) * 1000),
    )
    if results:
        logger.info(
            "other_yahoo_sample query=%r urls=%s",
            query,
            [c.url[:70] for c in results[:5]],
        )
    return results

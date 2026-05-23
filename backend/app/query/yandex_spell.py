"""Optional spell correction via Yandex web search suggestion HTML."""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import parse_qs, unquote_plus, urlparse

from curl_cffi import requests as curl_requests
from selectolax.parser import HTMLParser

from app.core.cache import cache_get, cache_set
from app.core.config import settings

logger = logging.getLogger(__name__)

_CORRECTION_PATTERNS = (
    re.compile(r"Исправлена опечатка[^«»\"']*[«\"']([^«»\"']+)[»\"']", re.IGNORECASE),
    re.compile(r"Возможно,\s*вы\s+имели\s+в\s+виду[^«»\"']*[«\"']([^«»\"']+)[»\"']", re.IGNORECASE),
)


def _cache_key(query: str) -> str:
    return f"query:spell:{query.strip().lower()}"


def _extract_from_href(href: str) -> str | None:
    if href.startswith("/"):
        href = f"https://yandex.ru{href}"
    parsed = urlparse(href)
    params = parse_qs(parsed.query)
    for key in ("text", "query"):
        values = params.get(key)
        if values and values[0].strip():
            return unquote_plus(values[0].strip())
    return None


def parse_yandex_spell_correction(html: str) -> str | None:
    for pattern in _CORRECTION_PATTERNS:
        match = pattern.search(html)
        if match:
            candidate = match.group(1).strip()
            if candidate and not candidate.startswith(("/", "http")):
                return candidate

    tree = HTMLParser(html)
    for node in tree.css("a"):
        href = node.attributes.get("href", "")
        text = node.text(strip=True)
        if not href or not text:
            continue
        if "search" not in href or len(text) < 2:
            continue
        parent_text = node.parent.text(strip=True).lower() if node.parent else ""
        if "исправлен" in parent_text or "имели в виду" in parent_text:
            return _extract_from_href(href) or text
    return None


def _fetch_yandex_search_html_sync(query: str) -> str:
    session = curl_requests.Session(impersonate="chrome120")
    response = session.get(
        "https://yandex.ru/search/",
        params={"text": query, "lr": "213"},
        headers={
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=settings.query_spell_timeout_seconds,
    )
    response.raise_for_status()
    return response.text


async def fetch_yandex_spell_correction(query: str) -> str | None:
    normalized = query.strip()
    if not normalized or not settings.query_spell_enabled:
        return None

    cached = cache_get(_cache_key(normalized))
    if isinstance(cached, str) and cached:
        return cached if cached.lower() != normalized.lower() else None
    if cache_get(_cache_key(normalized) + ":miss"):
        return None

    try:
        html = await asyncio.wait_for(
            asyncio.to_thread(_fetch_yandex_search_html_sync, normalized),
            timeout=settings.query_spell_timeout_seconds + 0.5,
        )
    except Exception as exc:
        logger.warning("Yandex spell fetch failed for %r: %s", normalized, exc)
        return None

    corrected = parse_yandex_spell_correction(html)
    if corrected and corrected.strip().lower() != normalized.lower():
        cache_set(_cache_key(normalized), corrected.strip(), settings.query_spell_cache_ttl_seconds)
        return corrected.strip()

    cache_set(_cache_key(normalized) + ":miss", "1", ttl_seconds=3600)
    return None

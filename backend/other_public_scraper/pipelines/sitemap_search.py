"""Fallback discovery: match query tokens against product URLs in shop sitemaps."""

from __future__ import annotations

import asyncio
import io
import logging
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from other_public_scraper.config import CATEGORY_PROTOTYPES, DOMAIN_BLACKLIST, settings
from other_public_scraper.jobs.build_mini_index import PRODUCT_URL_RE
from other_public_scraper.ml.query_classifier import classify_query
from other_public_scraper.models import UrlCandidate
from other_public_scraper.storage.meili import search_meili
from other_public_scraper.transport import fetch_html

logger = logging.getLogger(__name__)

_SITEMAP_CACHE: dict[str, tuple[float, list[str]]] = {}
_SITEMAP_CACHE_TTL = 3600


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _is_blacklisted(url: str) -> bool:
    domain = _domain(url)
    return domain in DOMAIN_BLACKLIST or any(b in domain for b in DOMAIN_BLACKLIST)


def _parse_locs(xml_text: str) -> list[str]:
    locs: list[str] = []
    try:
        stream = io.BytesIO(xml_text.encode("utf-8", errors="ignore"))
        for _event, elem in ET.iterparse(stream, events=("end",)):
            tag = elem.tag.split("}")[-1]
            if tag == "loc" and elem.text:
                locs.append(elem.text.strip())
            elem.clear()
    except ET.ParseError as exc:
        logger.warning("sitemap parse error: %s", exc)
    return locs


_CATEGORY_URL_HINTS = {
    "tires": ("shina", "shiny", "tyre", "tires", "wheel", "disk", "шин", "резин", "колес"),
    "orgtech": ("noutbuk", "notebook", "printer", "monitor", "phone", "smartfon", "ноут", "принтер"),
    "clothes": ("odezhd", "kurtka", "dress", "boot", "jeans", "одеж", "куртк", "плать"),
}


_QUERY_CATEGORY_KEYWORDS = {
    "tires": ("шин", "резин", "колес", "диск", "tyre", "tire"),
    "orgtech": ("ноут", "принтер", "монитор", "комп", "phone", "смартф"),
    "clothes": ("одеж", "курт", "плать", "ботин", "джинс"),
}


def _query_tokens(query: str) -> list[str]:
    lower = query.lower()
    tokens = [token for token in re.split(r"\W+", lower) if len(token) > 2]
    category = classify_query(query)
    for cat, keywords in _QUERY_CATEGORY_KEYWORDS.items():
        if category == cat or any(keyword in lower for keyword in keywords):
            tokens.extend(_CATEGORY_URL_HINTS.get(cat, ()))
            if cat in CATEGORY_PROTOTYPES:
                tokens.extend(CATEGORY_PROTOTYPES[cat].split())
            break
    return list(dict.fromkeys(tokens))


def _url_matches_query(url: str, tokens: list[str]) -> bool:
    if not tokens:
        return True
    haystack = url.lower()
    return any(token in haystack for token in tokens)


async def _discover_domains() -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()

    for raw in settings.other_precrawl_domains.split(","):
        domain = raw.strip().lower().replace("www.", "")
        if domain and domain not in seen:
            seen.add(domain)
            domains.append(domain)

    if settings.other_meili_read_enabled:
        meili_hits = await search_meili("", limit=50)
        for hit in meili_hits:
            domain = (hit.domain or _domain(hit.url)).replace("www.", "")
            if domain and domain not in seen:
                seen.add(domain)
                domains.append(domain)

    return domains


async def _fetch_sitemap_locs(domain: str) -> list[str]:
    now = time.time()
    cached = _SITEMAP_CACHE.get(domain)
    if cached and now - cached[0] < _SITEMAP_CACHE_TTL:
        return cached[1]

    locs: list[str] = []
    for url in (f"https://{domain}/sitemap.xml", f"https://www.{domain}/sitemap.xml"):
        result = await fetch_html(url)
        if result is None:
            continue
        locs.extend(_parse_locs(result.body))
        product_sitemaps = [loc for loc in locs if re.search(r"sitemap", loc, re.I)]
        for sitemap_url in product_sitemaps[:4]:
            child = await fetch_html(sitemap_url)
            if child is not None:
                locs.extend(_parse_locs(child.body))

    _SITEMAP_CACHE[domain] = (now, locs)
    return locs


async def search_sitemap_urls(query: str, *, limit: int = 20) -> list[UrlCandidate]:
    tokens = _query_tokens(query)
    domains = await _discover_domains()
    if not domains:
        return []

    results: list[UrlCandidate] = []
    seen: set[str] = set()

    async def _scan_domain(domain: str) -> list[UrlCandidate]:
        locs = await _fetch_sitemap_locs(domain)
        hits: list[UrlCandidate] = []
        for loc in locs:
            if not loc.startswith("http") or _is_blacklisted(loc):
                continue
            if domain.replace("www.", "") not in _domain(loc):
                continue
            if not PRODUCT_URL_RE.search(loc):
                continue
            if not _url_matches_query(loc, tokens):
                continue
            key = loc.split("#")[0]
            if key in seen:
                continue
            seen.add(key)
            slug = urlparse(loc).path.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ")
            hits.append(
                UrlCandidate(
                    url=loc,
                    domain=_domain(loc),
                    title=slug or query,
                    snippet=slug,
                    source="sitemap",
                )
            )
            if len(hits) >= limit:
                break
        return hits

    groups = await asyncio.gather(*[_scan_domain(domain) for domain in domains[:8]])
    for group in groups:
        results.extend(group)
        if len(results) >= limit:
            break

    logger.info(
        "other_sitemap query=%r domains=%d results=%d",
        query,
        len(domains),
        len(results),
    )
    return results[:limit]

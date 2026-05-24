"""Expand catalog/listing pages into product URL candidates."""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser

from other_public_scraper.config import settings
from other_public_scraper.models import UrlCandidate
from other_public_scraper.transport import fetch_html
from other_public_scraper.url_heuristics import is_rejected_url

logger = logging.getLogger(__name__)

_PRODUCT_PATH_RE = re.compile(
    r"(?:"
    r"/product[s]?/"
    r"|/goods/"
    r"|/item/"
    r"|/tovar/"
    r"|/card/"
    r"|/catalog/\d+"
    r"|/razmer/"
    r")",
    re.IGNORECASE,
)

_TIRE_SIZE_RE = re.compile(r"\d{3}[-/]\d{2}[-/]R?\d{2}", re.IGNORECASE)
_NUMERIC_ID_RE = re.compile(r"/\d{5,}")

_CATALOG_PATH_RE = re.compile(
    r"(?:"
    r"/catalog/"
    r"|/category/"
    r"|/categories/"
    r"|/search"
    r"|/shiny"
    r"|/auto/"
    r")",
    re.IGNORECASE,
)

_SKIP_PATH_RE = re.compile(
    r"(?:"
    r"/actions/"
    r"|/articles/"
    r"|/news/"
    r"|/blog/"
    r"|/about/"
    r"|/contacts/"
    r"|/bookmark/"
    r"|/petition"
    r"|/ajax_"
    r"|/note\?"
    r")",
    re.IGNORECASE,
)


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


_RE_STORE_CATALOG_RE = re.compile(r"/catalog/([A-Za-z0-9_-]+)/?", re.IGNORECASE)
_CATEGORY_SLUGS = frozenset({
    "naushniki", "smartfony", "noutbuki", "planshety", "monitory", "shiny", "tyres",
})


def _is_product_url(url: str) -> bool:
    if is_rejected_url(url):
        return False
    path = urlparse(url).path
    if _SKIP_PATH_RE.search(path):
        return False
    lowered = path.lower()
    if "/all_sizes/" in lowered or "/category/" in lowered:
        return False
    if _TIRE_SIZE_RE.search(path):
        return True
    if _NUMERIC_ID_RE.search(path):
        return True
    if _PRODUCT_PATH_RE.search(path):
        return True
    segments = [part for part in path.split("/") if part]
    if "catalog" in segments and segments[-1]:
        last = segments[-1]
        if last.lower() in _CATEGORY_SLUGS or last.lower().startswith("brand_"):
            return False
        if len(segments) == 2:
            return True
        if last.isdigit() or re.search(r"\d{4,}", last):
            return True
        if len(segments) >= 5 and re.search(r"\d", last):
            return True
    return False


def _needs_expansion(url: str) -> bool:
    if is_rejected_url(url):
        return False
    return not _is_product_url(url)


def _extract_links(html: str, base_url: str) -> tuple[list[str], list[str]]:
    tree = HTMLParser(html)
    base_host = urlparse(base_url).netloc.lower()
    products: list[str] = []
    catalogs: list[str] = []
    seen: set[str] = set()

    for link in tree.css("a[href]"):
        href = link.attributes.get("href", "")
        if not href or href.startswith("#"):
            continue
        full = urljoin(base_url, href).split("#")[0]
        host = urlparse(full).netloc.lower()
        if host != base_host:
            continue
        if is_rejected_url(full):
            continue
        if _SKIP_PATH_RE.search(urlparse(full).path):
            continue
        if full in seen:
            continue
        seen.add(full)
        if _is_product_url(full):
            products.append(full)
        elif _CATALOG_PATH_RE.search(urlparse(full).path) or urlparse(full).path in ("", "/"):
            catalogs.append(full)

    for match in _RE_STORE_CATALOG_RE.finditer(html):
        sku = match.group(1)
        if sku.lower() in _CATEGORY_SLUGS or sku.lower().startswith("brand_"):
            continue
        full = urljoin(base_url, f"/catalog/{sku}/")
        if full in seen or is_rejected_url(full):
            continue
        seen.add(full)
        if _is_product_url(full):
            products.append(full)

    return products, catalogs


async def _harvest_one(
    candidate: UrlCandidate,
    *,
    per_listing: int,
    max_depth: int,
) -> list[UrlCandidate]:
    queue: list[tuple[str, int]] = [(candidate.url, 0)]
    seen_pages: set[str] = {candidate.url.split("#")[0]}
    products: list[str] = []
    fetches = 0
    max_fetches = max(2, max_depth + 1)

    while queue and len(products) < per_listing and fetches < max_fetches:
        page_url, depth = queue.pop(0)
        result = await fetch_html(page_url)
        fetches += 1
        if result is None:
            continue
        page_products, page_catalogs = _extract_links(result.body, page_url)
        for link in page_products:
            if link not in products:
                products.append(link)
            if len(products) >= per_listing:
                break
        if depth >= max_depth or len(products) >= per_listing:
            continue
        for catalog_url in page_catalogs[:8]:
            key = catalog_url.split("#")[0]
            if key in seen_pages:
                continue
            seen_pages.add(key)
            queue.append((catalog_url, depth + 1))

    return [
        UrlCandidate(
            url=link,
            domain=_domain(link),
            title=candidate.title,
            snippet=candidate.snippet,
            source=f"{candidate.source}+catalog",
            similarity=candidate.similarity,
        )
        for link in products
    ]


async def expand_listing_candidates(
    candidates: list[UrlCandidate],
    *,
    per_listing: int | None = None,
    max_depth: int | None = None,
) -> list[UrlCandidate]:
    """Replace listing/homepage URLs with product URLs discovered via shallow crawl."""
    per_listing = per_listing or settings.other_catalog_harvest_per_listing
    max_depth = max_depth if max_depth is not None else settings.other_catalog_harvest_depth
    listings = [c for c in candidates if _needs_expansion(c.url)]
    direct = [c for c in candidates if not _needs_expansion(c.url)]
    if not listings:
        return candidates

    harvested_groups = await asyncio.gather(
        *[
            _harvest_one(item, per_listing=per_listing, max_depth=max_depth)
            for item in listings[: settings.other_catalog_harvest_max_listings]
        ]
    )
    harvested: list[UrlCandidate] = []
    seen = {c.url.split("#")[0] for c in direct}
    for group in harvested_groups:
        for item in group:
            key = item.url.split("#")[0]
            if key in seen:
                continue
            seen.add(key)
            harvested.append(item)

    merged = direct + listings[: min(4, len(listings))] + harvested
    seen_merge: set[str] = set()
    deduped: list[UrlCandidate] = []
    for item in merged:
        key = item.url.split("#")[0]
        if key in seen_merge:
            continue
        seen_merge.add(key)
        deduped.append(item)
    merged = deduped
    logger.info(
        "other_catalog_harvest listings=%d harvested=%d kept_direct=%d",
        len(listings),
        len(harvested),
        len(direct),
    )
    return merged

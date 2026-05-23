"""Fallback catalog URLs when live search returns too few orgtech hits."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from other_public_scraper.models import UrlCandidate

_IPHONE_QUERY_RE = re.compile(r"(?:айфон|iphone)\s*(\d{1,2})", re.IGNORECASE)


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def orgtech_seed_candidates(query: str) -> list[UrlCandidate]:
    match = _IPHONE_QUERY_RE.search(query)
    if not match:
        return []
    generation = match.group(1)
    slug = f"iphone_{generation}" if generation else "iphone_15"
    dash_slug = f"iphone-{generation}"
    seeds = [
        f"https://cmstore.ru/catalog/smartfony/apple_iphone/{slug}/",
        f"https://re-store.ru/smartfony/apple/{dash_slug}/",
        f"https://shop.mts.ru/catalog/smartfony/apple/{dash_slug}/",
        f"https://biggeek.ru/catalog/apple-{dash_slug}",
    ]
    return [
        UrlCandidate(
            url=url,
            domain=_domain(url),
            title=query,
            snippet="",
            source="seed",
        )
        for url in seeds
    ]

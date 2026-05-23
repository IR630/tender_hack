"""Fallback catalog URLs when live search returns too few optics hits."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from other_public_scraper.models import UrlCandidate

_OPTICS_QUERY_RE = re.compile(r"очк", re.IGNORECASE)


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def optics_seed_candidates(query: str) -> list[UrlCandidate]:
    if not _OPTICS_QUERY_RE.search(query):
        return []
    seeds = [
        "https://www.letu.ru/browse/optika/ochki",
        "https://www.optic-city.ru/ochki_s_dioptrijami/",
        "https://ochkarik.ru/catalog/ochki/",
        "https://ochkarik.ru/catalog/solntsezashchitnye_ochki/",
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

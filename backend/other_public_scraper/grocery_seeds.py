"""Fallback grocery catalog URLs when live search returns category pages only."""

from __future__ import annotations

from urllib.parse import urlparse

from other_public_scraper.models import UrlCandidate

_GROCERY_HINTS = (
    "морожен",
    "молок",
    "хлеб",
    "сыр",
    "колбас",
    "продукт",
    "еда",
    "напит",
)


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_grocery_query(query: str) -> bool:
    lowered = query.lower()
    return any(hint in lowered for hint in _GROCERY_HINTS)


def grocery_seed_candidates(query: str) -> list[UrlCandidate]:
    if not is_grocery_query(query):
        return []
    seeds = [
        "https://online.metro-cc.ru/search?q=" + query.replace(" ", "+"),
        "https://www.vkusvill.ru/search/?q=" + query.replace(" ", "+"),
    ]
    return [
        UrlCandidate(url=url, domain=_domain(url), title=query, snippet="", source="seed")
        for url in seeds
    ]

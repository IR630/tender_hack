"""Fallback catalog URLs when live search returns too few orgtech hits."""

from __future__ import annotations

import re
from urllib.parse import quote_plus, urlparse

from other_public_scraper.models import UrlCandidate

_IPHONE_QUERY_RE = re.compile(r"(?:айфон|iphone)\s*(\d{1,2})", re.IGNORECASE)
_MOUSE_QUERY_RE = re.compile(r"\b(?:мыш|mouse|мышк)", re.IGNORECASE)
_KEYBOARD_QUERY_RE = re.compile(r"\b(?:клавиат|keyboard)", re.IGNORECASE)
_PRINTER_QUERY_RE = re.compile(r"\b(?:принтер|printer|мфу)\b", re.IGNORECASE)
_E2E4_REGION_HOSTS = {
    "moscow": "moscow.e2e4online.ru",
    "spb": "spb.e2e4online.ru",
    "novosibirsk": "novosibirsk.e2e4online.ru",
}


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _e2e4_catalog_urls(region_id: str | None, slug: str) -> list[str]:
    urls: list[str] = []
    host = _E2E4_REGION_HOSTS.get((region_id or "").strip().lower())
    if host:
        urls.append(f"https://{host}/catalog/{slug}/")
    urls.append(f"https://www.e2e4online.ru/catalog/{slug}/")
    return urls


def orgtech_seed_candidates(query: str, region_id: str | None = None) -> list[UrlCandidate]:
    seeds: list[str] = []

    if _MOUSE_QUERY_RE.search(query):
        seeds.extend(
            [
                *_e2e4_catalog_urls(region_id, "myshi-18"),
                "https://www.technocity.ru/catalog/13/",
                "https://www.dns-shop.ru/catalog/17a8a69116404e77/mysi/",
                "https://www.citilink.ru/catalog/myshi/",
                "https://www.mvideo.ru/komputernye-aksessuary-24/myshi-183",
            ]
        )
    if _KEYBOARD_QUERY_RE.search(query):
        seeds.extend(
            [
                *_e2e4_catalog_urls(region_id, "klaviatury-19"),
                "https://www.dns-shop.ru/catalog/17a89aab16404e77/klaviatury/",
                "https://www.citilink.ru/search/?text=клавиатура",
            ]
        )
    if _PRINTER_QUERY_RE.search(query):
        seeds.extend(
            [
                *_e2e4_catalog_urls(region_id, "printery-86"),
                "https://www.dns-shop.ru/catalog/17a8d26216404e77/printery/",
                "https://www.citilink.ru/search/?text=принтер",
            ]
        )

    match = _IPHONE_QUERY_RE.search(query)
    if match:
        generation = match.group(1)
        slug = f"iphone_{generation}" if generation else "iphone_15"
        dash_slug = f"iphone-{generation}"
        seeds.extend(
            [
                f"https://cmstore.ru/catalog/smartfony/apple_iphone/{slug}/",
                f"https://re-store.ru/smartfony/apple/{dash_slug}/",
                f"https://shop.mts.ru/catalog/smartfony/apple/{dash_slug}/",
                f"https://biggeek.ru/catalog/apple-{dash_slug}",
            ]
        )

    return [
        UrlCandidate(
            url=quote_plus(url, safe=":/?=&%-._"),
            domain=_domain(url),
            title=query,
            snippet="",
            source="seed",
        )
        for url in seeds
    ]

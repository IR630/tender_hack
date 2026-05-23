from __future__ import annotations

import re
from urllib.parse import urlparse

from other_public_scraper.models import OtherExtractResult
from other_public_scraper.parsers.adapters.base import get_adapter
from ozon_public_scraper.parsers.json_ld import extract_product_from_json_ld
from ozon_public_scraper.parsers.og_extractor import extract_og
from ozon_public_scraper.parsers.price import parse_price

PRICE_RE = re.compile(r"(\d[\d\s\u202f]*)\s*(?:₽|руб\.?)", re.IGNORECASE)


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def extract_product_from_html(
    html: str, url: str, *, relevance_score: float = 0.0
) -> OtherExtractResult | None:
    adapter = get_adapter(url)
    raw: dict = {}
    method = "json_ld"
    confidence = 0.8

    if adapter is not None:
        raw = adapter.extract(html, url)
        method = raw.get("extraction_method", "adapter")
        confidence = float(raw.get("confidence", 1.0))
    else:
        raw = extract_product_from_json_ld(html)
        method = "json_ld" if raw.get("title") else method
        if not raw.get("title") or raw.get("price_raw") is None:
            og = extract_og(html, url=url)
            if og.title:
                raw["title"] = og.title
            if og.description:
                raw["description"] = og.description
            if og.image_url:
                raw["image_url"] = og.image_url
            if og.price_rub:
                raw["price_rub"] = og.price_rub
            method = "og" if og.title else method
            confidence = 0.6

    title = str(raw.get("title") or "").strip()
    price_rub = raw.get("price_rub")
    if price_rub is None:
        price_rub = parse_price(str(raw.get("price_raw") or ""))
    if price_rub is None:
        match = PRICE_RE.search(html[:80000])
        if match:
            price_rub = parse_price(match.group(1))
            method = "regex"
            confidence = min(confidence, 0.4)

    image_url = str(raw.get("image_url") or "").strip()
    description = str(raw.get("description") or "").strip()
    if not title or not price_rub or not image_url:
        return None

    if not image_url.startswith("http"):
        return None

    return OtherExtractResult(
        title=title,
        description=description,
        price_rub=int(price_rub),
        image_url=image_url,
        product_url=url,
        source_domain=_domain(url),
        confidence=confidence,
        extraction_method=method,
        relevance_score=relevance_score,
    )

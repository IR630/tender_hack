from __future__ import annotations

import asyncio
import gzip
import io
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from ozon_public_scraper.config import (
    CATEGORY_KEYWORDS,
    GOOGLEBOT_UA,
    SITEMAP_INDEX_URL,
    YANDEXBOT_UA,
    settings,
)
from ozon_public_scraper.logging_config import get_logger
from ozon_public_scraper.models import ProductUrl
from ozon_public_scraper.transport import fetch_url

logger = get_logger("ozon_public.pipelines.sitemap")

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
PRODUCT_PATH_RE = re.compile(r"/product/(.+)-(\d+)/?$")


def _log_category_assumptions() -> None:
    for category, keywords in CATEGORY_KEYWORDS.items():
        logger.warning(
            "category_keyword_assumed",
            context={"category": category, "assumed_keyword": ",".join(keywords[:5])},
        )


def classify_slug(slug: str) -> str | None:
    slug_lower = slug.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in slug_lower:
                return category
    return None


def parse_product_url(url: str) -> ProductUrl | None:
    parsed = urlparse(url)
    if parsed.netloc not in ("www.ozon.ru", "ozon.ru"):
        return None
    m = PRODUCT_PATH_RE.search(parsed.path)
    if not m:
        return None
    slug, numeric_id = m.group(1), m.group(2)
    category = classify_slug(slug)
    return ProductUrl(
        numeric_id=numeric_id,
        slug=slug,
        url=url if url.startswith("http") else f"https://www.ozon.ru{parsed.path}",
        category=category,
    )


async def fetch_robots_txt() -> str:
    result = await fetch_url("https://www.ozon.ru/robots.txt", apply_ozon_limit=True)
    text = result.body.decode("utf-8", errors="replace")[:5000]
    logger.info(
        "robots_txt_fetched",
        context={
            "status_code": result.status_code,
            "allows_sitemap": "Sitemap:" in text or "sitemap" in text.lower(),
            "snippet": text[:300],
        },
    )
    return text


async def _fetch_sitemap_with_fallback(url: str) -> bytes:
    for ua, label in [(None, "desktop"), (YANDEXBOT_UA, "yandexbot"), (GOOGLEBOT_UA, "googlebot")]:
        result = await fetch_url(url, user_agent=ua, accept="application/xml,text/xml,*/*")
        if result.status_code == 200 and result.body[:1] in (b"<", b"\x1f"):
            if label != "desktop":
                logger.info(
                    "sitemap_ua_switched_to_bot",
                    context={"ua_used": label, "reason": "desktop_403_or_blocked", "url": url},
                )
            return result.body
    logger.error("sitemap_fetch_failed", context={"url": url})
    return b""


def _iter_sitemap_locs(xml_bytes: bytes) -> list[str]:
    locs: list[str] = []
    for _event, elem in ET.iterparse(io.BytesIO(xml_bytes), events=("end",)):
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "loc" and elem.text:
            locs.append(elem.text.strip())
        elem.clear()
    return locs


def _stream_product_urls(xml_bytes: bytes, categories: set[str] | None = None):
    if xml_bytes[:2] == b"\x1f\x8b":
        xml_bytes = gzip.decompress(xml_bytes)
    for _event, elem in ET.iterparse(io.BytesIO(xml_bytes), events=("end",)):
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag == "loc" and elem.text:
            product = parse_product_url(elem.text.strip())
            if product and (categories is None or product.category in categories):
                yield product
        elem.clear()


async def rebuild_from_sitemap(
    *,
    max_products: int = 5000,
    categories: set[str] | None = None,
) -> list[ProductUrl]:
    _log_category_assumptions()
    await fetch_robots_txt()

    index_body = await _fetch_sitemap_with_fallback(SITEMAP_INDEX_URL)
    if not index_body:
        return []

    child_sitemaps = _iter_sitemap_locs(index_body)
    logger.info("sitemap_index_parsed", context={"child_count": len(child_sitemaps)})

    products: list[ProductUrl] = []
    seen: set[str] = set()

    for sitemap_url in child_sitemaps:
        if len(products) >= max_products:
            break
        if "product" not in sitemap_url.lower() and "categor" not in sitemap_url.lower():
            continue

        await asyncio.sleep(settings.ozon_sitemap_pause_seconds)
        logger.info(
            "rate_limit_applied",
            context={
                "domain": "ozon.ru",
                "waited_ms": int(settings.ozon_sitemap_pause_seconds * 1000),
                "reason": "sitemap_child_pause",
            },
        )

        body = await _fetch_sitemap_with_fallback(sitemap_url)
        if not body:
            continue

        for product in _stream_product_urls(body, categories=categories):
            if product.numeric_id in seen:
                continue
            seen.add(product.numeric_id)
            products.append(product)
            if len(products) >= max_products:
                break

    logger.info("sitemap_rebuild_done", context={"products_collected": len(products)})
    return products

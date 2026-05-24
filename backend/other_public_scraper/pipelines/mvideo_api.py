from __future__ import annotations

import asyncio
import re
import time

from curl_cffi import requests as curl_requests

from other_public_scraper.config import DESKTOP_UA, settings
from other_public_scraper.models import OtherExtractResult

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _clean_html_text(value: str) -> str:
    return re.sub(r"\s+", " ", _HTML_TAG_RE.sub(" ", value or "")).strip()


def _price_map(payload: dict) -> dict[str, int]:
    prices: dict[str, int] = {}
    for item in payload.get("body", {}).get("materialPrices", []):
        product_id = str(item.get("productId") or "")
        price = item.get("price") or {}
        value = price.get("salePrice") or price.get("basePromoPrice") or price.get("basePrice")
        if product_id and value:
            prices[product_id] = int(value)
    return prices


def _image_url(detail: dict) -> str:
    images = detail.get("images") or []
    if not images:
        return ""
    path = str(images[0]).lstrip("/")
    return f"https://img.mvideo.ru/{path}"


def _product_url(detail: dict) -> str:
    product_id = str(detail.get("productId") or "")
    slug = str(detail.get("nameTranslit") or "").strip("/")
    if slug and product_id:
        return f"https://www.mvideo.ru/products/{slug}-{product_id}"
    return f"https://www.mvideo.ru/product/{product_id}" if product_id else "https://www.mvideo.ru/"


def _fetch_mvideo_products(query: str, *, limit: int) -> list[OtherExtractResult]:
    session = curl_requests.Session(impersonate="chrome120")
    category_url = "https://www.mvideo.ru/komputernye-aksessuary-24/myshi-183"
    headers = {
        "User-Agent": DESKTOP_UA,
        "Accept-Language": "ru-RU,ru;q=0.9",
    }
    session.get(category_url, headers=headers, timeout=settings.other_request_timeout)
    headers.update(
        {
            "Accept": "application/json",
            "Referer": category_url,
            "X-Requested-With": "XMLHttpRequest",
        }
    )
    search = session.get(
        "https://www.mvideo.ru/bff/products/v2/search",
        params={"query": query, "offset": "0", "limit": str(limit)},
        headers=headers,
        timeout=settings.other_request_timeout,
    )
    if search.status_code >= 400:
        return []
    product_ids = [
        str(product_id)
        for product_id in search.json().get("body", {}).get("products", [])
        if product_id
    ][:limit]
    if not product_ids:
        return []

    prices_resp = session.get(
        "https://www.mvideo.ru/bff/products/prices",
        params={"productIds": ",".join(product_ids)},
        headers=headers,
        timeout=settings.other_request_timeout,
    )
    prices = _price_map(prices_resp.json()) if prices_resp.status_code < 400 else {}

    results: list[OtherExtractResult] = []
    for product_id in product_ids:
        detail_resp = session.get(
            "https://www.mvideo.ru/bff/product-details",
            params={"productId": product_id},
            headers=headers,
            timeout=settings.other_request_timeout,
        )
        if detail_resp.status_code >= 400:
            continue
        detail = detail_resp.json().get("body") or {}
        price_rub = prices.get(product_id)
        title = str(detail.get("name") or "").strip()
        if not title or price_rub is None:
            continue
        results.append(
            OtherExtractResult(
                title=title,
                description=_clean_html_text(str(detail.get("description") or "")),
                price_rub=price_rub,
                image_url=_image_url(detail),
                product_url=_product_url(detail),
                source_domain="www.mvideo.ru",
                confidence=0.75,
                extraction_method="mvideo_bff",
                relevance_score=0.0,
            )
        )
    return results


async def search_mvideo_products(
    query: str,
    region_id: str,
    *,
    limit: int = 5,
) -> list[OtherExtractResult]:
    if region_id != "moscow":
        return []
    t0 = time.perf_counter()
    try:
        return await asyncio.to_thread(_fetch_mvideo_products, query, limit=limit)
    except Exception:
        return []
    finally:
        _ = int((time.perf_counter() - t0) * 1000)

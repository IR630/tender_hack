from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from other_public_scraper.parsers.listing_grid import extract_dom_listing_products
from other_public_scraper.models import OtherExtractResult
from other_public_scraper.parsers.adapters.base import get_adapter
from ozon_public_scraper.parsers.json_ld import (
    extract_all_products_from_json_ld,
    extract_product_from_json_ld,
)
from ozon_public_scraper.parsers.og_extractor import extract_og
from ozon_public_scraper.parsers.price import parse_price

_PRICE_ATTR_RE = re.compile(
    r'(?:data-price|data-product-price|priceValue)\s*=\s*["\']?(\d[\d\s]*)["\']?',
    re.IGNORECASE,
)
_ITEMPROP_PRICE_RE = re.compile(
    r'itemprop=["\']price["\'][^>]*content=["\'](\d+)["\']',
    re.IGNORECASE,
)
_CATEGORY_TITLE_RE = re.compile(
    r"(?:купить\s+от|интернет[-\s]магазин|каталог\s+\w+\s+купить)",
    re.IGNORECASE,
)
PRICE_RE = re.compile(r"(\d[\d\s\u202f]*)\s*(?:₽|руб\.?)", re.IGNORECASE)
_MIN_PLAUSIBLE_PRICE_RUB = 50


def _first_plausible_price(text: str) -> int | None:
    for match in PRICE_RE.finditer(text or ""):
        parsed = parse_price(match.group(1))
        if parsed is not None and parsed >= _MIN_PLAUSIBLE_PRICE_RUB:
            return parsed
    return None


def _extract_price_from_html(html: str, raw: dict) -> int | None:
    price_rub = raw.get("price_rub")
    if price_rub is None:
        price_rub = parse_price(str(raw.get("price_raw") or ""))
    if price_rub is not None:
        price_rub = int(price_rub)
        if price_rub >= _MIN_PLAUSIBLE_PRICE_RUB:
            return price_rub
        text_price = _first_plausible_price(
            " ".join(
                str(raw.get(key) or "")
                for key in ("title", "description", "price_raw")
            )
        )
        if text_price is not None:
            return text_price
    for pattern in (_ITEMPROP_PRICE_RE, _PRICE_ATTR_RE):
        match = pattern.search(html[:120000])
        if match:
            parsed = parse_price(match.group(1))
            if parsed and parsed >= _MIN_PLAUSIBLE_PRICE_RUB:
                return parsed
    plausible = _first_plausible_price(html[:120000])
    if plausible is not None:
        return plausible
    if price_rub is not None and price_rub > 0:
        return int(price_rub)
    return None


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _path_segments(url: str) -> list[str]:
    return [part for part in urlparse(url).path.split("/") if part]


def _looks_like_listing_slug(slug: str) -> bool:
    listing_slugs = {
        "naushniki", "smartfony", "noutbuki", "planshety", "monitory", "shiny", "tyres",
    }
    listing_prefixes = ("myshi", "mysi", "klaviatury", "printery")
    return slug in listing_slugs or slug.startswith(listing_prefixes)


def is_product_page_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    if re.search(
        r"/(?:product(?:s)?|goods|details|shop/details|catalog/(?:item|detail))/",
        path,
    ):
        return True
    segments = _path_segments(url)
    if not segments:
        return False
    if segments[-1].isdigit():
        return True
    if "product" in segments:
        return True
    if "catalog" in segments and len(segments) == 2:
        slug = segments[-1].lower()
        if slug.startswith("brand_"):
            return False
        if _looks_like_listing_slug(slug):
            return False
        if not any(c.isdigit() for c in slug) and "-" in slug:
            return False
        return True
    return False


def is_category_listing(title: str, url: str) -> bool:
    title_lower = title.lower()
    if " купить в " in title_lower and not any(c.isdigit() for c in title):
        return True
    if is_product_page_url(url):
        return False
    if _CATEGORY_TITLE_RE.search(title):
        return True
    segments = _path_segments(url)
    if "catalog" in segments and len(segments) <= 4:
        return True
    if segments and segments[-1] in {"iphone-15", "iphone-16", "smartfony"}:
        return True
    return False


def _raw_to_result(
    raw: dict,
    *,
    fallback_url: str,
    relevance_score: float,
    method: str,
    confidence: float,
) -> OtherExtractResult | None:
    title = str(raw.get("title") or "").strip()
    price_rub = raw.get("price_rub")
    if price_rub is None:
        price_rub = parse_price(str(raw.get("price_raw") or ""))
    image_url = str(raw.get("image_url") or "").strip()
    if image_url:
        image_url = urljoin(fallback_url, image_url)
    if image_url.startswith("data:image") or not image_url.startswith("http"):
        image_url = ""
        
    description = str(raw.get("description") or "").strip()
    
    product_url = str(raw.get("product_url") or "").strip()
    if not product_url:
        if "listing" in method:
            return None
        product_url = fallback_url
        
    if not title or not price_rub or not product_url.startswith("http"):
        return None
    return OtherExtractResult(
        title=title,
        description=description,
        price_rub=int(price_rub),
        image_url=image_url,
        product_url=product_url,
        source_domain=_domain(product_url),
        confidence=confidence,
        extraction_method=method,
        relevance_score=relevance_score,
    )


def extract_products_from_listing_html(
    html: str,
    page_url: str,
    *,
    relevance_score: float = 0.0,
    max_items: int = 12,
) -> list[OtherExtractResult]:
    """Extract multiple products from a catalog/listing page (JSON-LD + DOM grid)."""
    results: list[OtherExtractResult] = []
    seen: set[str] = set()
    for raw in extract_all_products_from_json_ld(html):
        item = _raw_to_result(
            raw,
            fallback_url=page_url,
            relevance_score=relevance_score,
            method="json_ld_listing",
            confidence=0.75,
        )
        if item is None or is_category_listing(item.title, item.product_url):
            continue
        key = item.product_url.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        results.append(item)
        if len(results) >= max_items:
            return results

    for raw in extract_dom_listing_products(html, page_url, max_items=max_items):
        item = _raw_to_result(
            raw,
            fallback_url=page_url,
            relevance_score=relevance_score,
            method="dom_listing",
            confidence=0.65,
        )
        if item is None or is_category_listing(item.title, item.product_url):
            continue
        key = item.product_url.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        results.append(item)
        if len(results) >= max_items:
            break
    return results


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
    price_rub = _extract_price_from_html(html, raw)
    if price_rub is None:
        return None
    if raw.get("price_rub") is None and raw.get("price_raw") in (None, ""):
        if _ITEMPROP_PRICE_RE.search(html[:120000]) or _PRICE_ATTR_RE.search(html[:120000]):
            method = "regex"
            confidence = min(confidence, 0.5)
        elif PRICE_RE.search(html[:120000]):
            method = "regex"
            confidence = min(confidence, 0.4)

    image_url = str(raw.get("image_url") or "").strip()
    
    if not image_url:
        from selectolax.parser import HTMLParser
        tree = HTMLParser(html)
        for img in tree.css("img"):
            src = (
                img.attributes.get("data-src")
                or img.attributes.get("data-lazy-src")
                or img.attributes.get("data-original")
                or img.attributes.get("src")
            )
            if src and not src.startswith("data:image"):
                image_url = src
                break

    if image_url:
        image_url = urljoin(url, image_url)
        
    if image_url.startswith("data:image") or not image_url.startswith("http"):
        image_url = ""

    description = str(raw.get("description") or "").strip()
    product_url = str(raw.get("product_url") or url).strip()
    if not title or not price_rub:
        return None

    return OtherExtractResult(
        title=title,
        description=description,
        price_rub=int(price_rub),
        image_url=image_url,
        product_url=product_url,
        source_domain=_domain(product_url),
        confidence=confidence,
        extraction_method=method,
        relevance_score=relevance_score,
    )

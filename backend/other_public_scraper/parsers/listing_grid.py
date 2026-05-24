"""DOM extractors for catalog/listing pages (browser-rendered retail grids)."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser

from ozon_public_scraper.parsers.price import parse_price

PRICE_RE = re.compile(r"(\d[\d\s\u202f]*)\s*(?:₽|&#8381;|руб\.?)", re.IGNORECASE)
_PRODUCT_HREF_RE = re.compile(
    r"/product/|/goods/|/item/|/catalog/detail/|/catalog/item/",
    re.IGNORECASE,
)


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _img_src(node) -> str:
    if node is None:
        return ""
    for img in node.css("img"):
        src = (
            img.attributes.get("data-src")
            or img.attributes.get("data-srcset")
            or img.attributes.get("src")
            or ""
        ).split()[0]
        if src and not src.startswith("data:"):
            return src
    return ""


def _price_from_node(node) -> int | None:
    if node is None:
        return None
    for key in ("data-product-price", "data-price", "content"):
        raw = node.attributes.get(key)
        if raw:
            parsed = parse_price(str(raw))
            if parsed:
                return parsed
    text = node.text(separator=" ", strip=True)
    if text:
        match = PRICE_RE.search(text)
        if match:
            parsed = parse_price(match.group(1))
            if parsed:
                return parsed
    chunk = node.html or ""
    match = PRICE_RE.search(chunk[:4000])
    if match:
        return parse_price(match.group(1))
    return None


def _extract_dns_cards(html: str, page_url: str, *, max_items: int) -> list[dict]:
    tree = HTMLParser(html)
    results: list[dict] = []
    seen: set[str] = set()
    for card in tree.css(".catalog-product"):
        link = card.css_first("a.catalog-product__name") or card.css_first(
            "a.catalog-product__image-link"
        )
        if link is None:
            continue
        href = (link.attributes.get("href") or "").strip()
        if not href:
            continue
        product_url = urljoin(page_url, href)
        key = product_url.split("#")[0]
        if key in seen:
            continue
        title_node = card.css_first(".catalog-product__name") or link
        title = title_node.text(separator=" ", strip=True) if title_node else ""
        if len(title) < 3:
            continue
        price_node = (
            card.css_first(".catalog-product__price")
            or card.css_first("[data-product-price]")
            or card.css_first(".product-buy__price")
        )
        price_rub = _price_from_node(price_node)
        if price_rub is None:
            price_rub = _price_from_node(card)
        if price_rub is None:
            continue
        image_url = urljoin(page_url, _img_src(card))
        seen.add(key)
        results.append(
            {
                "title": title,
                "description": "",
                "price_rub": price_rub,
                "image_url": image_url,
                "product_url": product_url,
            }
        )
        if len(results) >= max_items:
            break
    return results


def _parse_plain_price(text: str) -> int | None:
    digits = re.sub(r"\D", "", text or "")
    if not digits or len(digits) > 8:
        return None
    value = int(digits)
    if value < 50 or value > 5_000_000:
        return None
    return value


def _extract_technocity_cards(html: str, page_url: str, *, max_items: int) -> list[dict]:
    tree = HTMLParser(html)
    results: list[dict] = []
    seen: set[str] = set()
    for card in tree.css("article.catalog-item, .catalog-item.item"):
        link = card.css_first("a[href*='/catalog/detail/']")
        if link is None:
            continue
        href = (link.attributes.get("href") or "").strip()
        product_url = urljoin(page_url, href)
        key = product_url.split("#")[0]
        if key in seen:
            continue
        title_node = card.css_first(".name") or card.css_first("a[href*='/catalog/detail/']")
        title = title_node.text(separator=" ", strip=True) if title_node else ""
        if len(title) < 5:
            raw = card.text(separator=" ", strip=True)
            title = raw[:160] if raw else ""
        price_node = card.css_first(".price-above-button") or card.css_first("[class*='price']")
        price_rub = _price_from_node(price_node)
        if price_rub is None and price_node:
            price_rub = _parse_plain_price(price_node.text(strip=True))
        if price_rub is None:
            continue
        image_url = urljoin(page_url, _img_src(card))
        seen.add(key)
        results.append(
            {
                "title": title,
                "description": "",
                "price_rub": price_rub,
                "image_url": image_url,
                "product_url": product_url,
            }
        )
        if len(results) >= max_items:
            break
    return results


def _extract_e2e4_cards(html: str, page_url: str, *, max_items: int) -> list[dict]:
    tree = HTMLParser(html)
    results: list[dict] = []
    seen: set[str] = set()
    for link in tree.css("a[href*='/catalog/item/']"):
        href = (link.attributes.get("href") or "").strip()
        if not href:
            continue
        product_url = urljoin(page_url, href.split("#")[0])
        key = product_url.split("#")[0]
        if key in seen:
            continue
        title = link.text(separator=" ", strip=True)
        if len(title) < 5:
            continue
        parent = link.parent
        price_rub = None
        for _ in range(10):
            if parent is None:
                break
            price_node = parent.css_first(".product-price") or parent.css_first(".price-current")
            if price_node:
                price_rub = _price_from_node(price_node) or _parse_plain_price(price_node.text(strip=True))
            if price_rub is None:
                price_rub = _price_from_node(parent)
            if price_rub is not None:
                break
            parent = parent.parent
        if price_rub is None:
            continue
        image_url = ""
        parent = link.parent
        for _ in range(10):
            if parent is None:
                break
            image_url = _img_src(parent)
            if image_url:
                break
            parent = parent.parent
        seen.add(key)
        results.append(
            {
                "title": title,
                "description": "",
                "price_rub": price_rub,
                "image_url": urljoin(page_url, image_url) if image_url else "",
                "product_url": product_url,
            }
        )
        if len(results) >= max_items:
            break
    return results


def _extract_technopark_cards(html: str, page_url: str, *, max_items: int) -> list[dict]:
    tree = HTMLParser(html)
    results: list[dict] = []
    seen: set[str] = set()
    selectors = (
        ".product-card",
        "[data-entity='item']",
        ".catalog-item",
        ".product-tile",
    )
    cards: list = []
    for selector in selectors:
        cards = tree.css(selector)
        if cards:
            break
    for card in cards:
        link = card.css_first("a[href*='/product/']") or card.css_first("a[href*='/catalog/']")
        if link is None:
            continue
        href = (link.attributes.get("href") or "").strip()
        if not href or not _PRODUCT_HREF_RE.search(href):
            continue
        product_url = urljoin(page_url, href)
        key = product_url.split("#")[0]
        if key in seen:
            continue
        title = link.attributes.get("title") or link.text(separator=" ", strip=True)
        if len(title) < 3:
            title_node = card.css_first("[class*='title']") or card.css_first("h3")
            title = title_node.text(separator=" ", strip=True) if title_node else ""
        if len(title) < 3:
            continue
        price_rub = _price_from_node(
            card.css_first("[class*='price']") or card.css_first("[data-price]")
        )
        if price_rub is None:
            price_rub = _price_from_node(card)
        if price_rub is None:
            continue
        image_url = urljoin(page_url, _img_src(card))
        seen.add(key)
        results.append(
            {
                "title": title,
                "description": "",
                "price_rub": price_rub,
                "image_url": image_url,
                "product_url": product_url,
            }
        )
        if len(results) >= max_items:
            break
    return results


def _extract_generic_cards(html: str, page_url: str, *, max_items: int) -> list[dict]:
    tree = HTMLParser(html)
    results: list[dict] = []
    seen: set[str] = set()
    for link in tree.css("a[href]"):
        href = (link.attributes.get("href") or "").strip()
        if not href or not _PRODUCT_HREF_RE.search(href):
            continue
        product_url = urljoin(page_url, href)
        key = product_url.split("#")[0]
        if key in seen:
            continue
        title = link.attributes.get("title") or link.text(separator=" ", strip=True)
        if len(title) < 5:
            continue
        parent = link.parent
        price_rub = None
        for _ in range(8):
            if parent is None:
                break
            price_rub = _price_from_node(parent)
            if price_rub is not None:
                break
            parent = parent.parent
        if price_rub is None:
            continue
        image_url = ""
        parent = link.parent
        for _ in range(8):
            if parent is None:
                break
            image_url = _img_src(parent)
            if image_url:
                break
            parent = parent.parent
        seen.add(key)
        results.append(
            {
                "title": title,
                "description": "",
                "price_rub": price_rub,
                "image_url": urljoin(page_url, image_url) if image_url else "",
                "product_url": product_url,
            }
        )
        if len(results) >= max_items:
            break
    return results


def extract_dom_listing_products(
    html: str,
    page_url: str,
    *,
    max_items: int = 12,
) -> list[dict]:
    host = _domain(page_url)
    if host == "dns-shop.ru" or host.endswith(".dns-shop.ru"):
        items = _extract_dns_cards(html, page_url, max_items=max_items)
        if items:
            return items
    if host == "technocity.ru" or host.endswith(".technocity.ru"):
        items = _extract_technocity_cards(html, page_url, max_items=max_items)
        if items:
            return items
    if "e2e4online.ru" in host:
        items = _extract_e2e4_cards(html, page_url, max_items=max_items)
        if items:
            return items
    if "technopark.ru" in host:
        items = _extract_technopark_cards(html, page_url, max_items=max_items)
        if items:
            return items
    return _extract_generic_cards(html, page_url, max_items=max_items)

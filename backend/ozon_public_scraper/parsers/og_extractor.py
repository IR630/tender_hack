from __future__ import annotations

from selectolax.parser import HTMLParser

from ozon_public_scraper.logging_config import get_logger
from ozon_public_scraper.models import RawOgData
from ozon_public_scraper.parsers.json_ld import extract_product_from_json_ld
from ozon_public_scraper.parsers.price import parse_price

logger = get_logger("ozon_public.parsers.og_extractor")


def _meta(tree: HTMLParser, prop: str) -> str | None:
    node = tree.css_first(f'meta[property="{prop}"]')
    if node and node.attributes.get("content"):
        return node.attributes["content"]
    node = tree.css_first(f'meta[name="{prop}"]')
    if node and node.attributes.get("content"):
        return node.attributes["content"]
    return None


def _link_rel(tree: HTMLParser, rel: str) -> str | None:
    node = tree.css_first(f'link[rel="{rel}"]')
    if node and node.attributes.get("href"):
        return node.attributes["href"]
    return None


def extract_og(html: str, *, url: str) -> RawOgData:
    tree = HTMLParser(html)
    data = RawOgData()
    extracted: list[str] = []
    missing: list[str] = []

    # title
    title = _meta(tree, "og:title")
    source = "og:title"
    if not title:
        tnode = tree.css_first("title")
        title = tnode.text(strip=True) if tnode else None
        source = "title"
    if not title:
        h1 = tree.css_first("h1")
        title = h1.text(strip=True) if h1 else None
        source = "h1"
    if title:
        data.title = title
        extracted.append("title")
        if source != "og:title":
            logger.info(
                "og_field_fallback_used",
                context={"url": url, "field": "title", "source_used": source},
            )
    else:
        missing.append("title")
        logger.warning("og_field_missing", context={"url": url, "field": "title"})

    # image
    image = _meta(tree, "og:image")
    img_source = "og:image"
    if not image:
        image = _link_rel(tree, "image_src")
        img_source = "link:image_src"
    if not image:
        img = tree.css_first(".product-image-container img, img[itemprop='image'], img")
        if img and img.attributes.get("src"):
            image = img.attributes["src"]
            img_source = "img:first"
    if image:
        data.image_url = image
        extracted.append("image_url")
        if img_source != "og:image":
            logger.info(
                "og_field_fallback_used",
                context={"url": url, "field": "image_url", "source_used": img_source},
            )
    else:
        missing.append("image_url")
        logger.warning("og_field_missing", context={"url": url, "field": "image_url"})

    # description
    desc = _meta(tree, "og:description")
    desc_source = "og:description"
    if not desc:
        desc = _meta(tree, "description")
        desc_source = "meta:description"
    if desc:
        data.description = desc
        extracted.append("description")
        if desc_source != "og:description":
            logger.info(
                "og_field_fallback_used",
                context={"url": url, "field": "description", "source_used": desc_source},
            )

    # price
    price_raw = _meta(tree, "product:price:amount")
    price_source = "product:price:amount"
    if not price_raw:
        ld = extract_product_from_json_ld(html)
        price_raw = ld.get("price_raw")
        price_source = "json-ld"
    if not price_raw:
        import re

        m = re.search(r"(\d[\d\s\u202f]*)\s*₽", html[:50000])
        if m:
            price_raw = m.group(1)
            price_source = "regex"
    price = parse_price(str(price_raw) if price_raw else None)
    if price is not None:
        data.price_rub = price
        extracted.append("price_rub")
        if price_source != "product:price:amount":
            logger.info(
                "og_field_fallback_used",
                context={"url": url, "field": "price_rub", "source_used": price_source},
            )
    else:
        missing.append("price_rub")
        if price_raw:
            logger.warning(
                "og_price_parsing_failed",
                context={"url": url, "raw_string": str(price_raw)[:100], "error": "parse_failed"},
            )
        else:
            logger.warning("og_field_missing", context={"url": url, "field": "price_rub"})

    currency = _meta(tree, "product:price:currency")
    if currency:
        data.currency = currency
        extracted.append("currency")

    availability = _meta(tree, "product:availability")
    if not availability:
        ld = extract_product_from_json_ld(html)
        availability = ld.get("availability")
    if availability:
        data.availability = availability
        extracted.append("availability")

    canonical = _link_rel(tree, "canonical")
    data.canonical_url = canonical or url
    extracted.append("canonical_url")

    data.fields_extracted = extracted
    data.fields_missing = missing
    return data

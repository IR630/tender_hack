from __future__ import annotations

import json
from typing import Any

from ozon_public_scraper.logging_config import get_logger

logger = get_logger("ozon_public.parsers.json_ld")


def extract_product_from_json_ld(html: str) -> dict[str, Any]:
    """Find first Product schema in JSON-LD blocks."""
    for product in extract_all_products_from_json_ld(html):
        return product
    return {}


def extract_all_products_from_json_ld(html: str) -> list[dict[str, Any]]:
    """Collect every Product node from JSON-LD blocks on the page."""
    products: list[dict[str, Any]] = []
    seen: set[str] = set()
    marker = 'type="application/ld+json"'
    pos = 0
    while True:
        start = html.find(marker, pos)
        if start == -1:
            break
        content_start = html.find(">", start) + 1
        content_end = html.find("</script>", content_start)
        if content_end == -1:
            break
        raw = html[content_start:content_end].strip()
        pos = content_end + 9
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for product in _collect_product_nodes(data):
            key = str(product.get("title") or "") + "|" + str(product.get("price_raw") or "")
            if key in seen:
                continue
            seen.add(key)
            products.append(product)
    return products


def _find_product_node(data: Any) -> dict[str, Any] | None:
    products = _collect_product_nodes(data)
    return products[0] if products else None


def _collect_product_nodes(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        out: list[dict[str, Any]] = []
        for item in data:
            out.extend(_collect_product_nodes(item))
        return out
    if not isinstance(data, dict):
        return []

    schema_type = data.get("@type", "")
    types = schema_type if isinstance(schema_type, list) else [schema_type]

    if "ListItem" in types:
        item = data.get("item")
        if isinstance(item, dict):
            return _collect_product_nodes(item)
        return []

    if "ItemList" in types:
        elements = data.get("itemListElement")
        if isinstance(elements, list):
            out: list[dict[str, Any]] = []
            for element in elements:
                out.extend(_collect_product_nodes(element))
            return out

    is_product = "Product" in types or schema_type == "Product"
    if is_product:
        parsed = _product_node_to_dict(data)
        return [parsed] if parsed else []

    graph = data.get("@graph")
    if isinstance(graph, list):
        return _collect_product_nodes(graph)
    return []


def _product_node_to_dict(data: dict[str, Any]) -> dict[str, Any] | None:
    out: dict[str, Any] = {}
    if isinstance(data.get("name"), str):
        out["title"] = data["name"]
    if isinstance(data.get("description"), str):
        out["description"] = data["description"]
    image = data.get("image")
    if isinstance(image, str):
        out["image_url"] = image
    elif isinstance(image, list) and image:
        first = image[0]
        if isinstance(first, str):
            out["image_url"] = first
        elif isinstance(first, dict) and isinstance(first.get("url"), str):
            out["image_url"] = first["url"]
    if isinstance(data.get("url"), str):
        out["product_url"] = data["url"]
    offers = data.get("offers")
    if isinstance(offers, dict):
        price = offers.get("price")
        if price is not None:
            out["price_raw"] = str(price)
        if isinstance(offers.get("url"), str):
            out["product_url"] = offers["url"]
    elif isinstance(offers, list) and offers:
        first_offer = offers[0]
        if isinstance(first_offer, dict):
            price = first_offer.get("price")
            if price is not None:
                out["price_raw"] = str(price)
            if isinstance(first_offer.get("url"), str):
                out["product_url"] = first_offer["url"]
    return out or None

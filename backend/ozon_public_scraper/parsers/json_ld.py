from __future__ import annotations

import json
from typing import Any

from ozon_public_scraper.logging_config import get_logger

logger = get_logger("ozon_public.parsers.json_ld")


def extract_product_from_json_ld(html: str) -> dict[str, Any]:
    """Find Product schema in JSON-LD blocks."""
    results: dict[str, Any] = {}
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
        product = _find_product_node(data)
        if product:
            results.update(product)
    return results


def _find_product_node(data: Any) -> dict[str, Any] | None:
    if isinstance(data, list):
        for item in data:
            found = _find_product_node(item)
            if found:
                return found
        return None
    if not isinstance(data, dict):
        return None

    schema_type = data.get("@type", "")
    if isinstance(schema_type, list):
        is_product = "Product" in schema_type
    else:
        is_product = schema_type == "Product"

    if is_product:
        out: dict[str, Any] = {}
        if isinstance(data.get("name"), str):
            out["title"] = data["name"]
        if isinstance(data.get("description"), str):
            out["description"] = data["description"]
        if isinstance(data.get("image"), str):
            out["image_url"] = data["image"]
        offers = data.get("offers")
        if isinstance(offers, dict):
            price = offers.get("price")
            if price is not None:
                out["price_raw"] = str(price)
            avail = offers.get("availability")
            if isinstance(avail, str):
                out["availability"] = avail
        return out or None

    graph = data.get("@graph")
    if isinstance(graph, list):
        return _find_product_node(graph)
    return None

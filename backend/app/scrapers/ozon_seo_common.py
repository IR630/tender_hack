"""Shared Ozon search page product extraction (JSON-first, HTML card fallback)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser, Node

logger = logging.getLogger(__name__)

OZON_BASE = "https://www.ozon.ru"
BADGE_TITLE_MARKERS = (
    "баллов за отзыв",
    "вау-цен",
    "распродажа",
    "цена что надо",
    "осталось",
    "шт",
)
PLACEHOLDER_IMAGE_MARKERS = (
    "data:image",
    "placeholder",
    "/wc50/",
    "multimedia-x/",
    "no-image",
)
CARD_SELECTORS = (
    "div.tile-root",
    "div.widget-search-result-container > div",
    '[data-widget="tileGridDesktop"] div.tile-root',
)
MAIN_GRID_ROOT_SELECTORS = (
    '[data-widget="tileGridDesktop"]',
    "div.widget-search-result-container",
)
SKIP_WIDGET_MARKERS = (
    "recommendation",
    "sponsored",
    "skushelf",
    "analog",
    "advert",
    "marketing",
    "sellerother",
    "history",
)
REJECT_CARD_MARKERS = (
    "реклама",
    "ozon global",
    "спонсор",
)
TITLE_SELECTORS = (
    "a.tile-hover-target span.tsBody500Medium",
    'a[href*="/product/"] span.tsBody500Medium',
    "span.tsBody500Medium",
)


def extract_products(html: str, *, max_results: int = 30) -> list[dict[str, str | int | None]]:
    """Backward-compatible alias for broad main-grid extraction."""
    return extract_broad_search_products(html, max_results=max_results)


def extract_broad_search_products(
    html: str,
    *,
    max_results: int = 36,
) -> list[dict[str, Any]]:
    """Extract preview products from the main search grid only (no recommendations)."""
    if not html:
        return []

    for extractor, label in (
        (_extract_broad_from_widget_states, "widget_states"),
        (_extract_broad_from_next_data, "next_data"),
    ):
        products = extractor(html, max_results=max_results)
        if products:
            logger.info("ozon_broad_search source=%s count=%d", label, len(products))
            return products[:max_results]

    products = _extract_broad_from_html_cards(html, max_results=max_results)
    if products:
        logger.info("ozon_broad_search source=html_cards count=%d", len(products))
    return products[:max_results]


def extract_product_enrichment(html: str) -> dict[str, Any]:
    """Extract description and characteristics from a product detail page."""
    result: dict[str, Any] = {"description": None, "characteristics": {}}
    if not html:
        return result

    for blob in (
        _load_script_json(html, r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>'),
        _load_nuxt_state(html),
    ):
        if blob is None:
            continue
        desc = _extract_description_from_json(blob)
        if desc and not result["description"]:
            result["description"] = desc
        chars = _extract_characteristics_from_json(blob)
        if chars:
            result["characteristics"].update(chars)

    for match in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            blob = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        nodes = blob if isinstance(blob, list) else [blob]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("@type") != "Product":
                continue
            if isinstance(node.get("description"), str) and not result["description"]:
                result["description"] = node["description"].strip()
            additional = node.get("additionalProperty")
            if isinstance(additional, list):
                for prop in additional:
                    if not isinstance(prop, dict):
                        continue
                    name = prop.get("name")
                    value = prop.get("value")
                    if name and value:
                        result["characteristics"][str(name)] = str(value)

    if not result["characteristics"]:
        result["characteristics"] = _extract_characteristics_from_html(html)
    if not result["description"]:
        result["description"] = _extract_description_from_html(html)
    return result


def _parse_price_rub(text: str | None) -> int:
    if not text:
        return 0
    digits = re.sub(r"[^\d]", "", text.replace("\u202f", "").replace("\u2009", "").replace(" ", ""))
    if not digits:
        return 0
    return int(digits) * 100


def _normalize_product_url(href: str) -> str:
    url = href if href.startswith("http") else urljoin(OZON_BASE, href)
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _is_placeholder_image(url: str) -> bool:
    lower = url.lower()
    return any(marker in lower for marker in PLACEHOLDER_IMAGE_MARKERS)


def _is_real_image(url: str | None) -> bool:
    return bool(url and url.startswith("http") and not _is_placeholder_image(url))


def _clean_title(title: str | None) -> str | None:
    if not title:
        return None
    cleaned = re.sub(r"\s+", " ", title).strip()
    if len(cleaned) < 3:
        return None
    lower = cleaned.lower()
    if any(marker in lower for marker in BADGE_TITLE_MARKERS):
        return None
    if cleaned in ("Распродажа", "Вау-цены"):
        return None
    return cleaned[:300]


def _extract_image_url(card: Node) -> str | None:
    picture = card.css_first("picture")
    if picture is not None:
        source = picture.css_first("source")
        if source is not None:
            srcset = source.attributes.get("srcset")
            if srcset:
                url = srcset.split(",")[0].strip().split()[0]
                if _is_real_image(url):
                    return url

    for img in card.css("img"):
        srcset = img.attributes.get("srcset")
        if srcset:
            url = srcset.split(",")[0].strip().split()[0]
            if _is_real_image(url):
                return url
        for attr in ("data-src", "data-original", "data-lazy-src", "data-lazy"):
            url = img.attributes.get(attr)
            if _is_real_image(url):
                return url
        src = img.attributes.get("src")
        if _is_real_image(src):
            return src
    return None


def build_search_preview_description(preview: dict[str, Any]) -> str:
    """Build a card description from search-page metadata (no product-page visit)."""
    lines: list[str] = []
    title = str(preview.get("title") or "").strip()
    if title:
        lines.append(title)

    rating = preview.get("rating")
    reviews_count = preview.get("reviews_count")
    rating_line: list[str] = []
    if isinstance(rating, (int, float)):
        rating_line.append(f"★ {rating:g}")
    if isinstance(reviews_count, int) and reviews_count > 0:
        rating_line.append(f"{reviews_count:,}".replace(",", " ") + " отзывов")
    if rating_line:
        lines.append(" · ".join(rating_line))

    badges = preview.get("badges")
    if isinstance(badges, list):
        badge_text = ", ".join(str(item).strip() for item in badges if str(item).strip())
        if badge_text:
            lines.append(badge_text)

    return "\n\n".join(lines).strip()


def _append_preview(
    products: list[dict[str, Any]],
    seen: set[str],
    *,
    title: str | None,
    price: int,
    url: str,
    image: str | None,
    max_results: int,
    rating: float | None = None,
    reviews_count: int | None = None,
    badges: list[str] | None = None,
) -> None:
    if len(products) >= max_results or price <= 0:
        return
    clean_title = _clean_title(title)
    if not clean_title:
        return
    normalized_url = _normalize_product_url(url)
    if normalized_url in seen:
        return
    seen.add(normalized_url)
    preview: dict[str, Any] = {
        "title": clean_title,
        "price": price,
        "url": normalized_url,
        "image": image if _is_real_image(image) else None,
        "rating": rating,
        "reviews_count": reviews_count,
        "badges": badges or [],
        "characteristics": {},
    }
    preview["description"] = build_search_preview_description(preview)
    products.append(preview)


def _append_product(
    products: list[dict[str, str | int | None]],
    seen: set[str],
    *,
    title: str | None,
    price: int,
    url: str,
    image: str | None,
    max_results: int,
) -> None:
    if len(products) >= max_results or price <= 0:
        return
    clean_title = _clean_title(title)
    if not clean_title:
        return
    normalized_url = _normalize_product_url(url)
    if normalized_url in seen:
        return
    seen.add(normalized_url)
    products.append(
        {
            "title": clean_title,
            "price": price,
            "url": normalized_url,
            "image": image if _is_real_image(image) else None,
        }
    )


def _item_from_json_obj(obj: dict[str, Any]) -> dict[str, Any] | None:
    link = obj.get("link") or obj.get("url") or obj.get("productUrl")
    action = obj.get("action")
    if isinstance(action, dict):
        link = link or action.get("link") or action.get("url")
    if not link or "/product/" not in str(link):
        return None

    title = obj.get("title") or obj.get("name")
    main_state = obj.get("mainState")
    if not title and isinstance(main_state, list):
        for block in main_state:
            if not isinstance(block, dict):
                continue
            atom = block.get("atom") or block.get("type")
            text = block.get("text") or block.get("value")
            if atom in ("textAtom", "title", "name") and isinstance(text, str):
                title = text
                break
            if isinstance(block.get("textAtom"), dict):
                title = block["textAtom"].get("text") or title

    price_raw = (
        obj.get("finalPrice")
        or obj.get("price")
        or obj.get("marketingPrice")
        or obj.get("originalPrice")
    )
    if price_raw is None and isinstance(main_state, list):
        for block in main_state:
            if not isinstance(block, dict):
                continue
            price_block = block.get("price") or block.get("priceV2")
            if isinstance(price_block, dict):
                price_raw = price_block.get("price") or price_block.get("finalPrice")
            if price_raw is not None:
                break

    price = price_raw if isinstance(price_raw, int) else _parse_price_rub(str(price_raw))
    if isinstance(price_raw, int) and price_raw < 100_000:
        price = price_raw * 100

    image = None
    for key in ("coverImage", "image", "previewImage"):
        val = obj.get(key)
        if isinstance(val, str) and _is_real_image(val):
            image = val
            break
    images = obj.get("images")
    if not image and isinstance(images, list):
        for val in images:
            if isinstance(val, str) and _is_real_image(val):
                image = val
                break
            if isinstance(val, dict):
                candidate = val.get("link") or val.get("url")
                if _is_real_image(candidate):
                    image = candidate
                    break
    tile_image = obj.get("tileImage")
    if not image and isinstance(tile_image, dict):
        for key in ("link", "url", "image"):
            candidate = tile_image.get(key)
            if _is_real_image(candidate):
                image = candidate
                break

    clean_title = _clean_title(str(title) if title else None)
    if not clean_title or price <= 0:
        return None
    return {
        "title": clean_title,
        "price": price,
        "url": _normalize_product_url(str(link)),
        "image": image,
    }


def _collect_json_items(node: Any, out: list[dict[str, Any]], *, depth: int = 0) -> None:
    if depth > 14:
        return
    if isinstance(node, dict):
        keys = set(node.keys())
        if keys & {"link", "title", "name", "sku", "mainState", "tileImage"}:
            parsed = _item_from_json_obj(node)
            if parsed:
                out.append(parsed)
        for key in ("items", "products", "searchResults", "tiles", "skuList"):
            value = node.get(key)
            if isinstance(value, list):
                for item in value:
                    _collect_json_items(item, out, depth=depth + 1)
        for key in ("widgetStates", "state", "shared", "catalog", "data"):
            value = node.get(key)
            if isinstance(value, (dict, list)):
                _collect_json_items(value, out, depth=depth + 1)
        if not keys & {"items", "products", "widgetStates", "state", "shared"}:
            for value in node.values():
                if isinstance(value, (dict, list)):
                    _collect_json_items(value, out, depth=depth + 1)
    elif isinstance(node, list):
        for item in node:
            _collect_json_items(item, out, depth=depth + 1)


def _json_blob_products(blob: Any, *, max_results: int) -> list[dict[str, str | int | None]]:
    collected: list[dict[str, Any]] = []
    _collect_json_items(blob, collected)
    products: list[dict[str, str | int | None]] = []
    seen: set[str] = set()
    for item in collected:
        _append_product(
            products,
            seen,
            title=item.get("title"),
            price=int(item.get("price") or 0),
            url=str(item.get("url") or ""),
            image=item.get("image"),
            max_results=max_results,
        )
    return products


def _load_script_json(html: str, pattern: str) -> Any | None:
    match = re.search(pattern, html, re.S)
    if not match:
        return None
    raw = match.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _load_nuxt_state(html: str) -> Any | None:
    match = re.search(r"window\.__NUXT__\.state\s*=\s*'(.+)'\s*;\s*window\.__NUXT__", html, re.S)
    if not match:
        match = re.search(
            r'window\.__NUXT__\.state\s*=\s*"(.+)"\s*;\s*window\.__NUXT__',
            html,
            re.S,
        )
    if not match:
        return None
    raw = match.group(1).replace("\\\\", "\\")
    try:
        state, _idx = json.JSONDecoder().raw_decode(raw)
        return state
    except json.JSONDecodeError:
        return None


def _extract_from_next_data(html: str, *, max_results: int) -> list[dict[str, str | int | None]]:
    blob = _load_script_json(html, r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>')
    if blob is None:
        return []
    return _json_blob_products(blob, max_results=max_results)


def _extract_from_nuxt_state(html: str, *, max_results: int) -> list[dict[str, str | int | None]]:
    blob = _load_nuxt_state(html)
    if blob is None:
        return []
    return _json_blob_products(blob, max_results=max_results)


def _extract_from_json_ld(html: str, *, max_results: int) -> list[dict[str, str | int | None]]:
    products: list[dict[str, str | int | None]] = []
    seen: set[str] = set()
    for match in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            blob = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        nodes = blob if isinstance(blob, list) else [blob]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("@type") != "Product":
                continue
            url = node.get("url") or node.get("offers", {}).get("url")
            if not url or "/product/" not in str(url):
                continue
            offers = node.get("offers")
            price_raw = offers.get("price") if isinstance(offers, dict) else node.get("price")
            price = _parse_price_rub(str(price_raw))
            image = node.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            _append_product(
                products,
                seen,
                title=str(node.get("name") or ""),
                price=price,
                url=str(url),
                image=str(image) if isinstance(image, str) else None,
                max_results=max_results,
            )
    return products


def _extract_from_embedded_items(
    html: str,
    *,
    max_results: int,
) -> list[dict[str, str | int | None]]:
    if "searchResultsV2" not in html and "/product/" not in html:
        return []
    products: list[dict[str, str | int | None]] = []
    seen: set[str] = set()
    pattern = re.compile(
        r'\{[^{}]*"link"\s*:\s*"(?P<link>/product/[^"]+)"[^{}]*"(?:title|name)"\s*:\s*"(?P<title>[^"]+)"[^{}]*\}',
        re.S,
    )
    for match in pattern.finditer(html):
        link = match.group("link")
        title = match.group("title").encode("utf-8").decode("unicode_escape")
        price_match = re.search(r'"(?:finalPrice|price)"\s*:\s*(?P<price>\d+)', match.group(0))
        price = int(price_match.group("price")) * 100 if price_match else 0
        image_match = re.search(
            r'"(?:coverImage|image)"\s*:\s*"(?P<image>https?://[^"]+)"',
            match.group(0),
        )
        image = image_match.group("image") if image_match else None
        _append_product(
            products,
            seen,
            title=title,
            price=price,
            url=link,
            image=image,
            max_results=max_results,
        )
    return products


def _is_rejected_card(card: Node) -> bool:
    text = card.text(strip=True).lower()
    if any(marker in text for marker in REJECT_CARD_MARKERS):
        return True
    node: Node | None = card
    while node is not None:
        widget = (node.attributes.get("data-widget") or "").lower()
        if widget and any(marker in widget for marker in SKIP_WIDGET_MARKERS):
            return True
        node = node.parent
    return False


def _find_main_grid_cards(tree: HTMLParser) -> list[Node]:
    for root_selector in MAIN_GRID_ROOT_SELECTORS:
        root = tree.css_first(root_selector)
        if root is None:
            continue
        cards = root.css("div.tile-root")
        if cards:
            return [card for card in cards if not _is_rejected_card(card)]
    cards = tree.css("div.tile-root")
    return [card for card in cards if not _is_rejected_card(card)]


def _extract_broad_from_html_cards(html: str, *, max_results: int) -> list[dict[str, Any]]:
    tree = HTMLParser(html)
    cards = _find_main_grid_cards(tree)
    products: list[dict[str, Any]] = []
    seen: set[str] = set()

    for card in cards:
        link_node = card.css_first('a[href*="/product/"]')
        if link_node is None:
            continue
        href = link_node.attributes.get("href", "")
        if not href:
            continue
        title = _extract_title_from_card(card)
        price = _extract_price_from_card(card)
        image = _extract_image_url(card)
        rating, reviews_count, badges = _extract_card_metadata(card)
        _append_preview(
            products,
            seen,
            title=title,
            price=price,
            url=href,
            image=image,
            max_results=max_results,
            rating=rating,
            reviews_count=reviews_count,
            badges=badges,
        )

    return products


def _extract_broad_from_next_data(html: str, *, max_results: int) -> list[dict[str, Any]]:
    blob = _load_script_json(html, r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>')
    if blob is None:
        return []
    items = _find_main_grid_items_in_json(blob)
    return _items_to_previews(items, max_results=max_results)


def _extract_broad_from_widget_states(html: str, *, max_results: int) -> list[dict[str, Any]]:
    blob = _load_nuxt_state(html)
    if blob is None:
        return []
    widget_states = blob.get("widgetStates") if isinstance(blob, dict) else None
    if not isinstance(widget_states, dict):
        return []
    items: list[dict[str, Any]] = []
    for key, raw in widget_states.items():
        key_lower = key.lower()
        if not any(token in key_lower for token in ("searchresultsv2", "tilegrid", "skugrid")):
            continue
        if any(token in key_lower for token in SKIP_WIDGET_MARKERS):
            continue
        state = raw
        if isinstance(raw, str):
            try:
                state = json.loads(raw)
            except json.JSONDecodeError:
                continue
        items.extend(_find_main_grid_items_in_json(state))
    return _items_to_previews(items, max_results=max_results)


def _find_main_grid_items_in_json(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(obj: Any, *, depth: int = 0, in_main: bool = False) -> None:
        if depth > 16:
            return
        if isinstance(obj, dict):
            component = str(obj.get("component") or obj.get("widgetName") or "").lower()
            origin = str(obj.get("originName") or obj.get("originComponent") or "").lower()
            is_main = in_main or any(
                token in component or token in origin
                for token in ("searchresultsv2", "tilegrid", "skugrid", "catalog.search")
            )
            is_skip = any(token in component or token in origin for token in SKIP_WIDGET_MARKERS)

            if is_main and not is_skip:
                for key in ("items", "products", "tiles", "skuList", "searchResults"):
                    value = obj.get(key)
                    if isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict):
                                parsed = _item_from_json_obj(item)
                                if parsed:
                                    found.append(parsed)
            for value in obj.values():
                walk(value, depth=depth + 1, in_main=is_main and not is_skip)
        elif isinstance(obj, list):
            for value in obj:
                walk(value, depth=depth + 1, in_main=in_main)

    walk(node)
    return found


def _items_to_previews(items: list[dict[str, Any]], *, max_results: int) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        title = str(item.get("title") or "")
        if any(marker in title.lower() for marker in REJECT_CARD_MARKERS):
            continue
        _append_preview(
            products,
            seen,
            title=title,
            price=int(item.get("price") or 0),
            url=str(item.get("url") or ""),
            image=item.get("image"),
            max_results=max_results,
            rating=item.get("rating"),
            reviews_count=item.get("reviews_count"),
            badges=item.get("badges"),
        )
    return products


def _extract_description_from_json(node: Any) -> str | None:
    if isinstance(node, dict):
        for key in ("description", "fullDescription", "text", "content"):
            value = node.get(key)
            if isinstance(value, str) and len(value.strip()) > 20:
                return value.strip()[:5000]
        for value in node.values():
            found = _extract_description_from_json(value)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _extract_description_from_json(value)
            if found:
                return found
    return None


def _extract_characteristics_from_json(node: Any) -> dict[str, str]:
    result: dict[str, str] = {}

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            name = obj.get("name") or obj.get("key") or obj.get("title")
            value = obj.get("value") or obj.get("text")
            if isinstance(name, str) and value is not None and str(value).strip():
                if name.lower() not in {"description", "title"}:
                    result[name.strip()] = str(value).strip()
            for key in (
                "characteristics",
                "attributes",
                "specs",
                "properties",
                "shortCharacteristics",
            ):
                block = obj.get(key)
                if isinstance(block, list):
                    for item in block:
                        if isinstance(item, dict):
                            n = item.get("name") or item.get("key")
                            v = item.get("value") or item.get("text")
                            if n and v:
                                result[str(n).strip()] = str(v).strip()
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(node)
    return result


def _extract_characteristics_from_html(html: str) -> dict[str, str]:
    tree = HTMLParser(html)
    result: dict[str, str] = {}
    for dl in tree.css("dl"):
        dts = dl.css("dt")
        dds = dl.css("dd")
        for dt, dd in zip(dts, dds, strict=False):
            name = dt.text(strip=True)
            value = dd.text(strip=True)
            if name and value:
                result[name] = value
    for row in tree.css('[data-widget="webCharacteristics"] tr, .characteristics tr'):
        cells = row.css("td, th")
        if len(cells) >= 2:
            name = cells[0].text(strip=True)
            value = cells[1].text(strip=True)
            if name and value:
                result[name] = value
    return result


def _extract_description_from_html(html: str) -> str | None:
    tree = HTMLParser(html)
    for selector in (
        '[data-widget="webDescription"]',
        '[data-widget="webDetailDescription"]',
        "#section-description",
        'div[itemprop="description"]',
    ):
        node = tree.css_first(selector)
        if node is not None:
            text = node.text(strip=True)
            if len(text) > 20:
                return text[:5000]
    meta = tree.css_first('meta[property="og:description"], meta[name="description"]')
    if meta is not None:
        content = meta.attributes.get("content")
        if content and len(content.strip()) > 20:
            return content.strip()[:5000]
    return None


def _find_cards(tree: HTMLParser) -> list[Node]:
    for selector in CARD_SELECTORS:
        cards = tree.css(selector)
        if cards:
            return cards
    return []


def _extract_card_metadata(card: Node) -> tuple[float | None, int | None, list[str]]:
    rating: float | None = None
    reviews_count: int | None = None
    badges: list[str] = []

    for node in card.css("span"):
        content = node.text(strip=True).replace("\xa0", " ")
        if rating is None and re.fullmatch(r"\d[.,]\d", content):
            try:
                rating = float(content.replace(",", "."))
            except ValueError:
                pass
        reviews_match = re.search(r"([\d\s\u2009\u202f]+)\s*отзыв", content, re.I)
        if reviews_match and reviews_count is None:
            digits = re.sub(
                r"[^\d]",
                "",
                reviews_match.group(1).replace("\u202f", "").replace("\u2009", "").replace(" ", ""),
            )
            if digits:
                reviews_count = int(digits)

    card_text = card.text(separator=" ", strip=True)
    for badge in ("Оригинал", "Распродажа"):
        if badge in card_text and badge not in badges:
            badges.append(badge)

    return rating, reviews_count, badges


def _extract_title_from_card(card: Node) -> str | None:
    for selector in TITLE_SELECTORS:
        for node in card.css(selector):
            title = _clean_title(node.text(strip=True))
            if title:
                return title
    link = card.css_first('a[href*="/product/"]')
    if link is not None:
        for attr in ("aria-label", "title"):
            title = _clean_title(link.attributes.get(attr))
            if title:
                return title
    return None


def _extract_price_from_card(card: Node) -> int:
    for selector in ("span.tsHead500Medium", "span.tsBody500Medium", "span.tsCompact500Medium"):
        for node in card.css(selector):
            text = node.text(strip=True)
            if "₽" in text:
                price = _parse_price_rub(text)
                if price > 0:
                    return price
    match = re.search(r"([\d\s\u2009\u202f]+)\s*₽", card.text(strip=True))
    return _parse_price_rub(match.group(0) if match else None)


def _extract_from_html_cards(html: str, *, max_results: int) -> list[dict[str, str | int | None]]:
    tree = HTMLParser(html)
    cards = _find_cards(tree)
    products: list[dict[str, str | int | None]] = []
    seen: set[str] = set()

    for card in cards:
        link_node = card.css_first('a[href*="/product/"]')
        if link_node is None:
            continue
        href = link_node.attributes.get("href", "")
        if not href:
            continue
        title = _extract_title_from_card(card)
        price = _extract_price_from_card(card)
        image = _extract_image_url(card)
        _append_product(
            products,
            seen,
            title=title,
            price=price,
            url=href,
            image=image,
            max_results=max_results,
        )

    return products

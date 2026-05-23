from __future__ import annotations

import asyncio
import html
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from difflib import SequenceMatcher
from urllib.parse import quote_plus, urljoin, urlparse

from curl_cffi import requests as curl_requests
from selectolax.parser import HTMLParser, Node

from app.core.cache import cache_get, cache_set
from app.core.config import settings
from app.core.models import Product, SearchRequest
from app.core.regions import resolve_region
from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://market.yandex.ru"
DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

PAGE_DELAY_SEC = 0.8
CARD_FETCH_WORKERS = 4
CARD_FETCH_TIMEOUT = 30
MAX_RESULTS = 20

# Stub heuristics — replace with ML/ranking later.
GARBAGE_KEYWORDS = (
    "чехол",
    "стекло",
    "плёнка",
    "пленка",
    "наклейк",
    "кабель",
    "зарядное",
    "зарядка",
    "адаптер",
    "бампер",
    "подставк",
    "ремешок",
    "гарнитур",
    "наушник",
)
QUERY_STOP_WORDS = frozenset(
    "и в на для по с из купить цена недорого новый новая новое the a an".split()
)
QUERY_TOKEN_ALIASES: dict[str, tuple[str, ...]] = {
    "телефон": ("телефон", "смартфон", "smartphone", "phone", "iphone", "айфон", "mobile"),
    "смартфон": ("смартфон", "телефон", "smartphone", "phone", "iphone", "айфон"),
    "ноутбук": ("ноутбук", "laptop", "notebook", "macbook"),
    "шины": ("шины", "шина", "tyre", "tire", "резин"),
    "очки": ("очки", "очков", "оправ", "ray-ban", "ray ban"),
}


@dataclass
class PageScanStats:
    accepted: int = 0
    duplicates: int = 0
    garbage: int = 0


def _is_blocked(html: str) -> bool:
    lowered = html.lower()
    return (
        "smartcaptcha" in lowered
        or "подтвердите, что запросы отправляли вы" in lowered
        or ("<title>403</title>" in lowered and len(html) < 10_000)
    )


def _parse_price_rub(text: str | None) -> int | None:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return None
    return int(digits) * 100


def _parse_rating(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"(\d+[.,]\d+|\d+)", text.replace(",", "."))
    if not match:
        return None
    return float(match.group(1))


def _parse_reviews(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"\((\d[\d\s]*)\)", text)
    if match:
        return int(re.sub(r"\s", "", match.group(1)))
    match = re.search(r"(\d[\d\s]*)\s*отзыв", text, re.IGNORECASE)
    if not match:
        return None
    return int(re.sub(r"\s", "", match.group(1)))


def _parse_bought_count(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"(\d[\d\s]*)\s*купил", text, re.IGNORECASE)
    if not match:
        return None
    return int(re.sub(r"\s", "", match.group(1)))


CHARACTERISTIC_LABELS = {
    "memory": "Память",
    "color": "Цвет",
    "variant": "Комплектация",
}


def _build_description(
    *,
    prose: str = "",
    characteristics: dict[str, str],
    rating: float | None,
    reviews_count: int | None,
    bought_count: int | None,
    delivery: str | None,
) -> str:
    lines: list[str] = []

    if prose.strip():
        lines.append(prose.strip())
        lines.append("")

    if characteristics:
        lines.append("Характеристики:")
        for label, value in characteristics.items():
            lines.append(f"• {label}: {value}")

    details: list[str] = []
    if rating is not None:
        rating_line = f"Рейтинг: {rating:g}"
        if reviews_count is not None:
            rating_line += f" ({reviews_count} отзывов)"
        details.append(rating_line)
    if bought_count is not None:
        details.append(f"Купили: {bought_count}")
    if delivery:
        details.append(f"Доставка: {delivery}")

    if details:
        if lines:
            lines.append("")
        lines.extend(details)

    return "\n".join(lines).strip()


def _parse_card_specs(html: str) -> dict[str, str]:
    tree = HTMLParser(html)
    specs: dict[str, str] = {}

    for label_el in tree.css('[data-auto="product-spec"]'):
        label = label_el.text(strip=True)
        if not label or label in specs:
            continue

        node = label_el.parent
        while node is not None and node.tag not in {"body", "html"}:
            full_text = node.text(strip=True)
            if "apiary" in full_text or "widgets" in full_text:
                node = node.parent
                continue
            if full_text.startswith(label):
                value = full_text[len(label) :].strip()
                if value and len(value) <= 200:
                    specs[label] = value
                    break
            node = node.parent

    return specs


def _parse_card_prose(html: str) -> str:
    tree = HTMLParser(html)
    description_el = tree.css_first('[data-auto="product-description"]')
    if not description_el:
        return ""
    prose = description_el.text(strip=True)
    prose = re.sub(r"\s+", " ", prose)
    return prose.strip()


def _card_page_url(product_url: str) -> str:
    return _product_url_key(product_url)


def _fetch_card_html(product_url: str) -> str:
    session = curl_requests.Session(impersonate="chrome120")
    response = session.get(
        _card_page_url(product_url),
        headers=DEFAULT_HEADERS,
        timeout=CARD_FETCH_TIMEOUT,
    )
    response.raise_for_status()
    return response.text


def _extract_snippet_meta(description: str) -> tuple[int | None, str | None]:
    bought_count: int | None = None
    delivery: str | None = None
    for line in description.splitlines():
        if line.startswith("Купили: "):
            digits = re.sub(r"[^\d]", "", line.removeprefix("Купили: "))
            if digits:
                bought_count = int(digits)
        if line.startswith("Доставка: "):
            delivery = line.removeprefix("Доставка: ").strip()
    return bought_count, delivery


def _enrich_product(product: Product) -> Product:
    try:
        html = _fetch_card_html(product.product_url)
    except Exception:
        logger.warning("Failed to fetch Yandex Market card page: %s", product.product_url)
        return product

    if _is_blocked(html):
        logger.warning("Yandex Market card page blocked: %s", product.product_url)
        return product

    prose = _parse_card_prose(html)
    card_specs = _parse_card_specs(html)
    characteristics = card_specs or product.characteristics
    bought_count, delivery = _extract_snippet_meta(product.description)

    return product.model_copy(
        update={
            "characteristics": characteristics,
            "description": _build_description(
                prose=prose,
                characteristics=characteristics,
                rating=product.rating,
                reviews_count=product.reviews_count,
                bought_count=bought_count,
                delivery=delivery,
            ),
            "confidence": 0.95 if card_specs or prose else product.confidence,
        }
    )


def _enrich_products(products: list[Product]) -> list[Product]:
    if not products:
        return products

    enriched: list[Product | None] = [None] * len(products)
    with ThreadPoolExecutor(max_workers=CARD_FETCH_WORKERS) as executor:
        future_to_index = {
            executor.submit(_enrich_product, product): index
            for index, product in enumerate(products)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                enriched[index] = future.result()
            except Exception:
                logger.exception(
                    "Failed to enrich Yandex Market product: %s",
                    products[index].product_url,
                )
                enriched[index] = products[index]

    return [product for product in enriched if product is not None]


def _clean_title_text(text: str) -> str:
    cleaned = html.unescape(text).replace("\xa0", " ").replace("&nbsp;", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"(?<=[A-Za-z0-9&])(?=[А-Яа-яЁё])", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _parse_snippet_title(title_el: Node) -> str:
    raw_attr = title_el.attributes.get("title")
    if raw_attr:
        return _clean_title_text(raw_attr)
    return _clean_title_text(title_el.text(strip=True))


def _extract_characteristics(title: str) -> dict[str, str]:
    characteristics: dict[str, str] = {}
    parts = [part.strip() for part in title.split(",") if part.strip()]
    if len(parts) > 1:
        characteristics["variant"] = ", ".join(parts[1:])
    memory = re.search(r"(\d+\s*(?:ГБ|GB|ТБ|TB))", title, re.IGNORECASE)
    if memory:
        characteristics["memory"] = memory.group(1)
    color = re.search(
        r"(?:,\s*)((?:черн|бел|син|красн|зел|фиолет|розов|золот|сереб|тёмн|темн)[^\,]*)",
        title,
        re.IGNORECASE,
    )
    if color:
        characteristics["color"] = color.group(1).strip()
    return characteristics


def _normalize_title(title: str) -> str:
    lowered = title.lower().replace("ё", "е")
    lowered = re.sub(r"[^\w\s]", " ", lowered, flags=re.UNICODE)
    return re.sub(r"\s+", " ", lowered).strip()


def _product_url_key(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def _query_tokens(query: str) -> list[str]:
    tokens: list[str] = []
    for raw in re.split(r"\s+", query.lower().replace("ё", "е")):
        token = re.sub(r"[^\w]", "", raw, flags=re.UNICODE)
        if len(token) < 2 or token in QUERY_STOP_WORDS:
            continue
        tokens.append(token)
    return tokens


def _expanded_query_tokens(query: str) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for token in _query_tokens(query):
        aliases = QUERY_TOKEN_ALIASES.get(token, (token,))
        for alias in (*aliases, token):
            if alias not in seen:
                seen.add(alias)
                expanded.append(alias)
    return expanded


def _title_matches_query(title_lower: str, query: str) -> bool:
    tokens = _query_tokens(query)
    if not tokens:
        return True
    expanded = _expanded_query_tokens(query)
    if any(alias in title_lower for alias in expanded):
        return True
    for token in tokens:
        if token in title_lower:
            return True
        if len(token) >= 3 and token[:3] in title_lower:
            return True
    return False


def _is_similar_title(left: str, right: str) -> bool:
    left_norm = _normalize_title(left)
    right_norm = _normalize_title(right)
    if left_norm == right_norm:
        return True
    return SequenceMatcher(None, left_norm, right_norm).ratio() >= 0.93


def _is_garbage_listing(title: str, query: str) -> bool:
    title_lower = title.lower().replace("ё", "е")
    query_tokens = _query_tokens(query)

    if query_tokens and not _title_matches_query(title_lower, query):
        return True

    if any(keyword in title_lower for keyword in GARBAGE_KEYWORDS):
        accessory_query = any(
            word in " ".join(query_tokens)
            for word in ("чехол", "стекло", "кабель", "заряд", "наушник")
        )
        if not accessory_query:
            return True

    return False


def _parse_search_html(html: str) -> list[Product]:
    tree = HTMLParser(html)
    products: list[Product] = []

    for article in tree.css("article"):
        title_el = article.css_first('[data-auto="snippet-title"]')
        if not title_el:
            continue

        title = _parse_snippet_title(title_el)
        if not title:
            continue

        price_el = article.css_first('[data-auto="snippet-price-current"]')
        link_el = article.css_first('a[href*="/product/"], a[href*="/card/"]')
        img_el = article.css_first("img")
        reviews_el = article.css_first('[data-auto="reviews"]')
        delivery_el = article.css_first('[data-auto="delivery-wrapper"]')

        href = link_el.attributes.get("href", "") if link_el else ""
        image = img_el.attributes.get("src", "") if img_el else ""
        price_kopecks = _parse_price_rub(price_el.text(strip=True) if price_el else None)

        if price_kopecks is None:
            continue

        reviews_text = reviews_el.text(strip=True) if reviews_el else None
        delivery_text = delivery_el.text(strip=True) if delivery_el else None
        if delivery_text:
            delivery_text = re.sub(r"\s+", " ", delivery_text.replace("\u2005", " ")).strip()

        characteristics = _extract_characteristics(title)
        rating = _parse_rating(reviews_text)
        reviews_count = _parse_reviews(reviews_text)
        bought_count = _parse_bought_count(reviews_text)

        products.append(
            Product(
                source="yandex_market",
                source_domain="market.yandex.ru",
                title=title,
                description=_build_description(
                    characteristics=characteristics,
                    rating=rating,
                    reviews_count=reviews_count,
                    bought_count=bought_count,
                    delivery=delivery_text,
                ),
                price=price_kopecks,
                image_url=image,
                product_url=urljoin(BASE_URL, href),
                characteristics=characteristics,
                rating=rating,
                reviews_count=reviews_count,
                confidence=0.9,
            )
        )

    return products


def _classify_listing(
    product: Product,
    query: str,
    seen_urls: set[str],
    seen_titles: list[str],
) -> str:
    url_key = _product_url_key(product.product_url)
    if url_key in seen_urls:
        return "duplicate"

    if any(_is_similar_title(product.title, seen_title) for seen_title in seen_titles):
        return "duplicate"

    if _is_garbage_listing(product.title, query):
        return "garbage"

    return "accepted"


def _collect_paginated_products(
    fetch_page_html,
    query: str,
    *,
    max_pages: int | None = None,
) -> list[Product]:
    page_limit = max_pages if max_pages is not None else settings.ym_search_max_pages
    accepted: list[Product] = []
    seen_urls: set[str] = set()
    seen_titles: list[str] = []

    for page in range(1, page_limit + 1):
        html = fetch_page_html(page)
        if not html or _is_blocked(html):
            logger.warning("Yandex Market page %s blocked or empty for query=%r", page, query)
            break

        page_products = _parse_search_html(html)
        if not page_products:
            logger.info("Yandex Market page %s has no parsable products, stop", page)
            break

        page_stats = PageScanStats()
        for product in page_products:
            verdict = _classify_listing(product, query, seen_urls, seen_titles)
            if verdict == "duplicate":
                page_stats.duplicates += 1
            elif verdict == "garbage":
                page_stats.garbage += 1
            else:
                accepted.append(product)
                seen_urls.add(_product_url_key(product.product_url))
                seen_titles.append(_normalize_title(product.title))
                page_stats.accepted += 1

        logger.debug(
            "Yandex Market page=%s accepted=%s duplicates=%s garbage=%s total=%s",
            page,
            page_stats.accepted,
            page_stats.duplicates,
            page_stats.garbage,
            len(accepted),
        )

        if page_stats.accepted == 0:
            logger.info(
                "Yandex Market stop at page=%s: no new products (duplicates=%s garbage=%s)",
                page,
                page_stats.duplicates,
                page_stats.garbage,
            )
            break

        if len(accepted) >= MAX_RESULTS:
            logger.info(
                "Yandex Market stop at page=%s: reached MAX_RESULTS=%s",
                page,
                MAX_RESULTS,
            )
            break

    return accepted[:MAX_RESULTS]


def _cache_key(region: str, query: str) -> str:
    return f"ym:search:{region}:{query.strip().lower()}"


async def _load_cached_products(region: str, query: str) -> list[Product] | None:
    if not settings.ym_cache_enabled:
        return None
    cached = await asyncio.to_thread(cache_get, _cache_key(region, query))
    if cached is None:
        return None
    logger.info("Yandex Market cache hit for query=%r region=%r", query, region)
    return [Product.model_validate(item) for item in cached]


async def _store_cached_products(region: str, query: str, products: list[Product]) -> None:
    if not settings.ym_cache_enabled or not products:
        return
    payload = [product.model_dump(mode="json") for product in products]
    await asyncio.to_thread(cache_set, _cache_key(region, query), payload)


def _apply_yandex_region(session: curl_requests.Session, yandex_market_id: int) -> None:
    region_value = str(yandex_market_id)
    session.cookies.set("yandex_gid", region_value, domain=".yandex.ru")
    session.cookies.set("yandex_gid", region_value, domain="market.yandex.ru")


def _fetch_products_sync(query: str, yandex_market_id: int) -> list[Product]:
    session = curl_requests.Session(impersonate="chrome120")
    _apply_yandex_region(session, yandex_market_id)
    session.get(f"{BASE_URL}/", headers=DEFAULT_HEADERS, timeout=20)

    def fetch_page_html(page: int) -> str:
        if page > 1:
            import time

            time.sleep(PAGE_DELAY_SEC)
        search_url = f"{BASE_URL}/search?text={quote_plus(query)}&page={page}&lr={yandex_market_id}"
        response = session.get(search_url, headers=DEFAULT_HEADERS, timeout=25)
        response.raise_for_status()
        return response.text

    products = _collect_paginated_products(fetch_page_html, query)
    if not products:
        logger.warning("Yandex Market pagination returned no products for query=%r", query)
        return products
    return _enrich_products(products)


async def _fetch_with_playwright(query: str, yandex_market_id: int) -> list[Product]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed, skipping YM browser fallback")
        return []

    page_html: dict[int, str] = {}

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(locale="ru-RU")
        await context.add_cookies(
            [
                {
                    "name": "yandex_gid",
                    "value": str(yandex_market_id),
                    "domain": ".yandex.ru",
                    "path": "/",
                }
            ]
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = await context.new_page()
        await page.goto(f"{BASE_URL}/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1500)

        for page_num in range(1, settings.ym_search_max_pages + 1):
            search_url = f"{BASE_URL}/search?text={quote_plus(query)}&page={page_num}&lr={yandex_market_id}"
            await page.goto(search_url, wait_until="networkidle", timeout=60000)
            html = await page.content()
            if _is_blocked(html):
                break
            page_html[page_num] = html
            if not _parse_search_html(html):
                break
            await page.wait_for_timeout(int(PAGE_DELAY_SEC * 1000))

        await browser.close()

    def fetch_page_html(page: int) -> str:
        return page_html.get(page, "")

    products = _collect_paginated_products(fetch_page_html, query)
    return _enrich_products(products)


class YandexMarketScraper(BaseScraper):
    source = "yandex_market"

    async def search(self, request: SearchRequest) -> list[Product]:
        self.clear_error()
        query = request.query.strip()
        if not query:
            return []

        region = resolve_region(request.region)

        cached = await _load_cached_products(region.id, query)
        if cached is not None:
            return cached

        try:
            products = await asyncio.to_thread(_fetch_products_sync, query, region.yandex_market_id)
            if products:
                await _store_cached_products(region.id, query, products)
                return products
            self.set_error("Яндекс Маркет не нашёл подходящих товаров по запросу")
        except Exception as exc:
            self.set_error(f"curl_cffi: {exc}")
            logger.exception("Yandex Market curl_cffi fetch failed for query=%r", query)

        try:
            products = await _fetch_with_playwright(query, region.yandex_market_id)
            if products:
                await _store_cached_products(region.id, query, products)
                return products
            if not self.last_error:
                self.set_error(
                    "Playwright fallback не вернул товаров (возможна капча или нет Chromium)"
                )
            return []
        except Exception as exc:
            self.set_error(f"Playwright: {exc}")
            logger.exception("Yandex Market Playwright fallback failed for query=%r", query)
            return []


scraper = YandexMarketScraper()

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin, urlsplit, urlunsplit

from curl_cffi import requests as curl_requests
from playwright.async_api import async_playwright
from selectolax.parser import HTMLParser

MOBILE_BASE_URL = "https://m.ozon.ru"
SOURCE = "ozon"
SOURCE_DOMAIN = "ozon.ru"
CURL_IMPERSONATE = "safari_ios"

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)

STOP_SIGNAL_COUNT = 5
MAX_PAGES = 8
PAGE_DELAY_SEC = 0.8
CARD_FETCH_WORKERS = 4
ENRICH_TOP_K = 8
CARD_FETCH_TIMEOUT = 20

NEXT_DATA_RE = re.compile(
    r"<script[^>]*id=[\"']__NEXT_DATA__[\"'][^>]*>(?P<body>.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
INITIAL_STATE_RE = re.compile(
    r"(?:window\.__INITIAL_STATE__|INITIAL_STATE)\s*=\s*(?P<body>\{.*?\})\s*;",
    re.IGNORECASE | re.DOTALL,
)
PRICE_RE = re.compile(r"(?P<price>\d[\d\s]{1,15})\s*(?:₽|руб\.?|RUB)", re.IGNORECASE)
RATING_RE = re.compile(r"(?P<rating>\d+[.,]\d+|\d+)\s*(?:из\s*5|/5|★)?", re.IGNORECASE)
REVIEWS_RE = re.compile(r"(?P<count>\d[\d\s]*)\s*отзыв", re.IGNORECASE)
COLOR_RE = re.compile(
    r"(?:черн|бел|син|красн|зел|сер|сереб|розов|голуб|беж|хаки|фиолет|желт)[^,;/]*",
    re.IGNORECASE,
)
MATERIAL_RE = re.compile(
    r"(?:хлопок|шерсть|кожа|полиэстер|лен|вискоза|замша|текстиль|металл)",
    re.IGNORECASE,
)
WS_RE = re.compile(r"\s+")

GARBAGE_KEYWORDS = (
    "чехол",
    "кейс",
    "пленка",
    "плёнка",
    "стекло",
    "кабель",
    "зарядка",
    "адаптер",
    "наклейк",
    "брелок",
    "ремешок",
    "держатель",
)
QUERY_STOP_WORDS = frozenset(
    "и в на для по с из купить цена недорого новый новая новое the a an".split()
)


@dataclass(slots=True)
class ParsedProduct:
    title: str
    price: int | None
    image_url: str
    product_url: str
    description: str = ""
    characteristics: dict[str, str] = field(default_factory=dict)
    source: str = SOURCE
    source_domain: str = SOURCE_DOMAIN
    rating: float | None = None
    reviews_count: int | None = None
    relevance_score: float = 0.0
    confidence: float = 0.0


@dataclass(slots=True)
class MethodAttempt:
    method: str
    status: str
    latency_ms: int
    products_found: int
    fields_completeness: dict[str, int]
    products: list[ParsedProduct] = field(default_factory=list)
    http_status: int | None = None
    response_size: int | None = None
    error: str | None = None
    notes: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SearchResult:
    query: str
    status: str
    method_used: str | None
    products: list[ParsedProduct] = field(default_factory=list)
    attempts: list[MethodAttempt] = field(default_factory=list)
    blocked_reason: str | None = None
    cache_hit: bool = False
    cached_at: str | None = None
    is_cached: bool = False
    latency_ms: int = 0


@dataclass(slots=True)
class PageScanStats:
    accepted: int = 0
    duplicates: int = 0
    garbage: int = 0


def _normalize_ws(value: str) -> str:
    return WS_RE.sub(" ", value).strip()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^\wа-яА-Я0-9]+", "_", value, flags=re.UNICODE).strip("_")
    return slug or "query"


def _normalize_product_url(value: str) -> str:
    if not value:
        return ""
    parts = urlsplit(urljoin(MOBILE_BASE_URL, value.strip()))
    host = "www.ozon.ru" if "ozon.ru" in parts.netloc else parts.netloc
    return urlunsplit(("https", host, parts.path, "", ""))


def _parse_price(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    return int(digits) if digits else None


def _parse_float(value: Any) -> float | None:
    if value is None or value is False:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None


def _parse_int(value: Any) -> int | None:
    if value is None or value is False:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        digits = re.sub(r"\D", "", value)
        return int(digits) if digits else None
    return None


def _detect_block_reason(text: str, status_code: int | None = None) -> str | None:
    lowered = text.lower()
    if status_code == 403:
        return "http_403"
    if "antibot challenge page" in lowered:
        return "antibot_challenge"
    if "доступ ограничен" in lowered:
        return "access_denied"
    if "captcha" in lowered:
        return "captcha"
    return None


def _extract_field_counts(products: list[ParsedProduct]) -> dict[str, int]:
    return {
        "title": sum(1 for product in products if bool(product.title)),
        "price": sum(1 for product in products if product.price is not None),
        "image": sum(1 for product in products if bool(product.image_url)),
        "url": sum(1 for product in products if bool(product.product_url)),
        "characteristics": sum(1 for product in products if len(product.characteristics) >= 1),
    }


def _classify_status(products: list[ParsedProduct]) -> str:
    if not products:
        return "failed"
    fields = _extract_field_counts(products)
    if all(fields[key] >= len(products) for key in ("title", "price", "image", "url")):
        return "success"
    return "partial"


def _iter_nodes(node: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(node, dict):
        items.append(node)
        for value in node.values():
            items.extend(_iter_nodes(value))
    elif isinstance(node, list):
        for item in node[:100]:
            items.extend(_iter_nodes(item))
    return items


def _find_nested_value(node: Any, keys: tuple[str, ...]) -> Any | None:
    if isinstance(node, dict):
        for key in keys:
            if key in node:
                return node[key]
        for value in node.values():
            found = _find_nested_value(value, keys)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node[:100]:
            found = _find_nested_value(item, keys)
            if found is not None:
                return found
    return None


def _parse_characteristics(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {
            _normalize_ws(str(key)): _normalize_ws(str(item))
            for key, item in value.items()
            if _normalize_ws(str(key)) and _normalize_ws(str(item))
        }
    if not isinstance(value, list):
        return {}

    result: dict[str, str] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _normalize_ws(str(item.get("name") or item.get("title") or ""))
        raw_value = item.get("value") or item.get("values") or item.get("text")
        if isinstance(raw_value, list):
            raw_value = ", ".join(str(part) for part in raw_value if part)
        parsed_value = _normalize_ws(str(raw_value or ""))
        if name and parsed_value:
            result[name] = parsed_value
    return result


def _build_description(
    *,
    prose: str = "",
    characteristics: dict[str, str],
    rating: float | None,
    reviews_count: int | None,
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

    if details:
        if lines:
            lines.append("")
        lines.extend(details)
    return "\n".join(lines).strip()


def _extract_title_characteristics(title: str) -> dict[str, str]:
    characteristics: dict[str, str] = {}
    if material := MATERIAL_RE.search(title):
        characteristics["Материал"] = material.group(0)
    if color := COLOR_RE.search(title):
        characteristics["Цвет"] = color.group(0)
    parts = [part.strip() for part in re.split(r"[,;/]", title) if part.strip()]
    if len(parts) > 1:
        characteristics["Вариант"] = ", ".join(parts[1:])
    return characteristics


def _normalize_title(title: str) -> str:
    lowered = title.lower().replace("ё", "е")
    lowered = re.sub(r"[^\w\s]", " ", lowered, flags=re.UNICODE)
    return re.sub(r"\s+", " ", lowered).strip()


def _query_tokens(query: str) -> list[str]:
    tokens: list[str] = []
    for raw in re.split(r"\s+", query.lower().replace("ё", "е")):
        token = re.sub(r"[^\w]", "", raw, flags=re.UNICODE)
        if len(token) < 2 or token in QUERY_STOP_WORDS:
            continue
        tokens.append(token)
    return tokens


def _is_similar_title(left: str, right: str) -> bool:
    left_norm = _normalize_title(left)
    right_norm = _normalize_title(right)
    if left_norm == right_norm:
        return True
    return SequenceMatcher(None, left_norm, right_norm).ratio() >= 0.93


def _is_garbage_listing(title: str, query: str) -> bool:
    title_lower = title.lower().replace("ё", "е")
    query_tokens = _query_tokens(query)

    if query_tokens and not any(token in title_lower for token in query_tokens):
        return True

    if any(keyword in title_lower for keyword in GARBAGE_KEYWORDS):
        accessory_query = any(
            word in " ".join(query_tokens)
            for word in ("чехол", "стекло", "кабель", "заряд", "ремешок")
        )
        if not accessory_query:
            return True

    return False


def _extract_json_blobs(html: str) -> list[Any]:
    payloads: list[Any] = []
    for pattern in (NEXT_DATA_RE, INITIAL_STATE_RE):
        for match in pattern.finditer(html):
            body = match.group("body").strip()
            try:
                payloads.append(json.loads(body))
            except json.JSONDecodeError:
                continue
    return payloads


def _with_description(product: ParsedProduct) -> ParsedProduct:
    product.description = _build_description(
        characteristics=product.characteristics,
        rating=product.rating,
        reviews_count=product.reviews_count,
    )
    return product


def _extract_products_from_payload(payload: Any, *, limit: int = 24) -> list[ParsedProduct]:
    products: list[ParsedProduct] = []
    seen_urls: set[str] = set()
    for node in _iter_nodes(payload):
        title = _find_nested_value(node, ("name", "title"))
        product_url = _find_nested_value(node, ("url", "href", "link", "productUrl"))
        price = _find_nested_value(node, ("price", "finalPrice", "cardPrice", "currentPrice"))
        image_url = _find_nested_value(node, ("image", "imageUrl", "src", "coverImage"))
        if isinstance(image_url, list):
            image_url = image_url[0] if image_url else ""

        normalized_url = _normalize_product_url(str(product_url or ""))
        if "/product/" not in normalized_url or not title:
            continue
        if normalized_url in seen_urls:
            continue

        characteristics = _parse_characteristics(
            _find_nested_value(node, ("characteristics", "attributes", "specs", "properties"))
            or {}
        )
        if not characteristics:
            characteristics = _extract_title_characteristics(str(title))

        product = ParsedProduct(
            title=_normalize_ws(str(title)),
            price=_parse_price(str(price)) if price is not None else None,
            image_url=urljoin(MOBILE_BASE_URL, str(image_url or "").split(" ", 1)[0]),
            product_url=normalized_url,
            characteristics=characteristics,
            rating=_parse_float(_find_nested_value(node, ("rating", "ratingValue", "score"))),
            reviews_count=_parse_int(
                _find_nested_value(node, ("reviewCount", "reviewsCount", "commentsCount"))
            ),
            confidence=0.7,
        )
        products.append(_with_description(product))
        seen_urls.add(normalized_url)
        if len(products) >= limit:
            break
    return products


def _parse_search_html(html: str) -> list[ParsedProduct]:
    for payload in _extract_json_blobs(html):
        products = _extract_products_from_payload(payload)
        if products:
            return products

    tree = HTMLParser(html)
    products: list[ParsedProduct] = []
    seen_urls: set[str] = set()

    for article in tree.css("article, div"):
        link_el = article.css_first('a[href*="/product/"]')
        if not link_el:
            continue

        href = link_el.attributes.get("href", "")
        product_url = _normalize_product_url(href)
        if not product_url or product_url in seen_urls:
            continue

        title = _normalize_ws(
            link_el.attributes.get("title")
            or link_el.attributes.get("aria-label")
            or link_el.text(separator=" ")
        )
        if len(title) < 3:
            continue

        block_text = _normalize_ws(article.text(separator=" "))
        price_match = PRICE_RE.search(block_text) or PRICE_RE.search(link_el.html or "")
        img_el = article.css_first("img")
        image_url = ""
        if img_el is not None:
            image_url = (
                img_el.attributes.get("src")
                or img_el.attributes.get("data-src")
                or img_el.attributes.get("srcset", "").split(" ", 1)[0]
            )
            image_url = urljoin(MOBILE_BASE_URL, image_url)

        rating = None
        reviews_count = None
        if rating_match := RATING_RE.search(block_text):
            rating = _parse_float(rating_match.group("rating"))
        if reviews_match := REVIEWS_RE.search(block_text):
            reviews_count = _parse_int(reviews_match.group("count"))

        characteristics = _extract_title_characteristics(title)
        product = ParsedProduct(
            title=title,
            price=_parse_price(price_match.group("price") if price_match else None),
            image_url=image_url,
            product_url=product_url,
            characteristics=characteristics,
            rating=rating,
            reviews_count=reviews_count,
            confidence=0.5,
        )
        products.append(_with_description(product))
        seen_urls.add(product_url)

    return products


def _classify_listing(
    product: ParsedProduct,
    query: str,
    seen_urls: set[str],
    seen_titles: list[str],
) -> str:
    if product.product_url in seen_urls:
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
    stop_signal_count: int = STOP_SIGNAL_COUNT,
    max_pages: int = MAX_PAGES,
) -> list[ParsedProduct]:
    accepted: list[ParsedProduct] = []
    seen_urls: set[str] = set()
    seen_titles: list[str] = []
    duplicate_signals = 0
    garbage_signals = 0

    for page in range(1, max_pages + 1):
        html = fetch_page_html(page)
        if not html or _detect_block_reason(html):
            break

        page_products = _parse_search_html(html)
        if not page_products:
            break

        page_stats = PageScanStats()
        for product in page_products:
            verdict = _classify_listing(product, query, seen_urls, seen_titles)
            if verdict == "duplicate":
                duplicate_signals += 1
                page_stats.duplicates += 1
            elif verdict == "garbage":
                garbage_signals += 1
                page_stats.garbage += 1
            else:
                accepted.append(product)
                seen_urls.add(product.product_url)
                seen_titles.append(_normalize_title(product.title))
                page_stats.accepted += 1

            if duplicate_signals >= stop_signal_count or garbage_signals >= stop_signal_count:
                return accepted

    return accepted


def _extract_card_characteristics(html: str) -> dict[str, str]:
    for payload in _extract_json_blobs(html):
        for node in _iter_nodes(payload):
            raw = _find_nested_value(
                node,
                ("characteristics", "attributes", "specs", "properties"),
            )
            characteristics = _parse_characteristics(raw or {})
            if characteristics:
                return characteristics

    tree = HTMLParser(html)
    characteristics: dict[str, str] = {}
    for row in tree.css("dl, tr, li"):
        text = _normalize_ws(row.text(separator=" "))
        if ":" not in text:
            continue
        key, value = text.split(":", 1)
        key = _normalize_ws(key)
        value = _normalize_ws(value)
        if key and value and len(key) < 120 and len(value) < 240:
            characteristics[key] = value
        if len(characteristics) >= 8:
            break
    return characteristics


def _extract_card_prose(html: str) -> str:
    tree = HTMLParser(html)
    meta = tree.css_first('meta[name="description"], meta[property="og:description"]')
    if meta is not None and meta.attributes.get("content"):
        return _normalize_ws(meta.attributes["content"])

    for selector in ("h1", "p", "div"):
        for node in tree.css(selector):
            text = _normalize_ws(node.text(separator=" "))
            if len(text) >= 80 and "доставка" not in text.lower():
                return text
    return ""


def _fetch_card_html(product_url: str, headers: dict[str, str]) -> str:
    session = curl_requests.Session(impersonate=CURL_IMPERSONATE)
    response = session.get(
        product_url,
        headers=headers,
        timeout=CARD_FETCH_TIMEOUT,
        allow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _enrich_product(product: ParsedProduct, headers: dict[str, str]) -> ParsedProduct:
    try:
        html = _fetch_card_html(product.product_url, headers)
    except Exception:
        return product

    if _detect_block_reason(html):
        return product

    prose = _extract_card_prose(html)
    card_characteristics = _extract_card_characteristics(html)
    characteristics = card_characteristics or product.characteristics
    description = _build_description(
        prose=prose,
        characteristics=characteristics,
        rating=product.rating,
        reviews_count=product.reviews_count,
    )
    enriched = ParsedProduct(**asdict(product))
    enriched.characteristics = characteristics
    enriched.description = description
    enriched.confidence = 0.95 if card_characteristics or prose else product.confidence
    return enriched


def _enrich_products(products: list[ParsedProduct], headers: dict[str, str]) -> list[ParsedProduct]:
    if not products:
        return products

    enriched: list[ParsedProduct | None] = [None] * len(products)
    with ThreadPoolExecutor(max_workers=CARD_FETCH_WORKERS) as executor:
        future_to_index = {
            executor.submit(_enrich_product, product, headers): index
            for index, product in enumerate(products[:ENRICH_TOP_K])
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                enriched[index] = future.result()
            except Exception:
                enriched[index] = products[index]

    for index in range(ENRICH_TOP_K, len(products)):
        enriched[index] = products[index]

    return [product for product in enriched if product is not None]


class OzonParser:
    def __init__(
        self,
        *,
        results_dir: str | Path = "results",
        timeout_seconds: float = 8.0,
        max_results: int = 12,
        headless: bool = True,
        demo_cache_path: str | Path | None = None,
        demo_fallback_enabled: bool = True,
    ) -> None:
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results
        self.headless = headless
        self.cache_dir = self.results_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.demo_cache_path = Path(
            demo_cache_path or Path(__file__).with_name("ozon_demo_cache.json")
        )
        self.demo_fallback_enabled = demo_fallback_enabled
        self.logger = self._build_logger()

    def _build_logger(self) -> logging.Logger:
        logger = logging.getLogger(f"ozon_parser.{id(self)}")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        handler = logging.FileHandler(self.results_dir / "ozon_parser.log")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
        return logger

    async def close(self) -> None:
        return None

    def _cache_path(self, query: str) -> Path:
        return self.cache_dir / f"{_slugify(query)}.json"

    def _save_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    def _load_search_cache(self, query: str) -> SearchResult | None:
        path = self._cache_path(query)
        if not path.exists():
            return None
        payload = json.loads(path.read_text())
        products = [ParsedProduct(**item) for item in payload.get("products", [])]
        attempts: list[MethodAttempt] = []
        for item in payload.get("attempts", []):
            item = dict(item)
            item["products"] = [ParsedProduct(**product) for product in item.get("products", [])]
            attempts.append(MethodAttempt(**item))
        return SearchResult(
            query=payload["query"],
            status=payload["status"],
            method_used=payload.get("method_used"),
            products=products,
            attempts=attempts,
            blocked_reason=payload.get("blocked_reason"),
            cache_hit=True,
            cached_at=payload.get("cached_at"),
            is_cached=payload.get("is_cached", False),
            latency_ms=payload.get("latency_ms", 0),
        )

    def _store_search_cache(self, result: SearchResult) -> None:
        payload = {
            "query": result.query,
            "status": result.status,
            "method_used": result.method_used,
            "products": [asdict(product) for product in result.products],
            "attempts": [asdict(attempt) for attempt in result.attempts],
            "blocked_reason": result.blocked_reason,
            "cached_at": result.cached_at,
            "is_cached": result.is_cached,
            "latency_ms": result.latency_ms,
        }
        self._save_json(self._cache_path(result.query), payload)

    def _mobile_headers(self) -> dict[str, str]:
        return {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "ru-RU,ru;q=0.9,en;q=0.8",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "upgrade-insecure-requests": "1",
            "user-agent": MOBILE_UA,
        }

    def _search_url(self, query: str, page: int) -> str:
        return f"{MOBILE_BASE_URL}/search/?text={quote_plus(query)}&page={page}"

    async def _search_mobile_html(self, query: str) -> MethodAttempt:
        started = time.perf_counter()
        headers = self._mobile_headers()

        def _run() -> MethodAttempt:
            session = curl_requests.Session(impersonate=CURL_IMPERSONATE)
            diagnostics: dict[str, Any] = {"pages": []}
            blocked_reason: str | None = None
            last_status: int | None = None
            last_response_size = 0

            try:
                session.get(MOBILE_BASE_URL, headers=headers, timeout=self.timeout_seconds)
            except Exception:
                pass

            def fetch_page_html(page: int) -> str:
                nonlocal blocked_reason, last_status, last_response_size
                if page > 1:
                    time.sleep(PAGE_DELAY_SEC)
                response = session.get(
                    self._search_url(query, page),
                    headers=headers,
                    timeout=self.timeout_seconds,
                    allow_redirects=True,
                )
                last_status = response.status_code
                last_response_size = len(response.text)
                page_block = _detect_block_reason(response.text, response.status_code)
                diagnostics["pages"].append(
                    {
                        "page": page,
                        "status": response.status_code,
                        "response_size": len(response.text),
                        "blocked_reason": page_block,
                    }
                )
                if page_block and blocked_reason is None:
                    blocked_reason = page_block
                return response.text

            products = _collect_paginated_products(fetch_page_html, query)
            products = _enrich_products(products[: self.max_results], headers)
            status = (
                _classify_status(products)
                if products
                else "blocked"
                if blocked_reason
                else "failed"
            )
            return MethodAttempt(
                method="mobile_html",
                status=status,
                latency_ms=int((time.perf_counter() - started) * 1000),
                products_found=len(products),
                fields_completeness=_extract_field_counts(products),
                products=products,
                http_status=last_status,
                response_size=last_response_size or None,
                error=blocked_reason,
                notes=(
                    "Paginated mobile HTML scan completed."
                    if products
                    else "No parsable products in curl_cffi page scan."
                ),
                diagnostics=diagnostics,
            )

        attempt = await asyncio.to_thread(_run)
        self.logger.info(
            json.dumps(
                {
                    "event": "mobile_html",
                    "query": query,
                    "status": attempt.status,
                    "products_found": attempt.products_found,
                    "http_status": attempt.http_status,
                    "error": attempt.error,
                },
                ensure_ascii=False,
            )
        )
        return attempt

    async def _search_mobile_browser(self, query: str) -> MethodAttempt:
        started = time.perf_counter()
        diagnostics: dict[str, Any] = {"pages": []}
        page_html: dict[int, str] = {}
        last_status: int | None = None
        blocked_reason: str | None = None

        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                context = await browser.new_context(
                    user_agent=MOBILE_UA,
                    locale="ru-RU",
                    viewport={"width": 430, "height": 932},
                    is_mobile=True,
                    has_touch=True,
                )
                page = await context.new_page()
                await page.goto(MOBILE_BASE_URL, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(1200)

                for page_num in range(1, MAX_PAGES + 1):
                    response = await page.goto(
                        self._search_url(query, page_num),
                        wait_until="networkidle",
                        timeout=max(30000, int(self.timeout_seconds * 1000)),
                    )
                    html = await page.content()
                    last_status = response.status if response is not None else None
                    page_block = _detect_block_reason(html, last_status)
                    diagnostics["pages"].append(
                        {
                            "page": page_num,
                            "status": last_status,
                            "response_size": len(html),
                            "blocked_reason": page_block,
                        }
                    )
                    if page_block:
                        blocked_reason = blocked_reason or page_block
                        break
                    page_html[page_num] = html
                    if not _parse_search_html(html):
                        break
                    await page.wait_for_timeout(int(PAGE_DELAY_SEC * 1000))

                await context.close()
                await browser.close()
        except Exception as exc:
            return MethodAttempt(
                method="mobile_browser",
                status="failed",
                latency_ms=int((time.perf_counter() - started) * 1000),
                products_found=0,
                fields_completeness=_extract_field_counts([]),
                error=type(exc).__name__,
                notes=str(exc),
                diagnostics=diagnostics,
            )

        def fetch_page_html(page: int) -> str:
            return page_html.get(page, "")

        products = _collect_paginated_products(fetch_page_html, query)
        products = _enrich_products(products[: self.max_results], self._mobile_headers())
        status = (
            _classify_status(products)
            if products
            else "blocked"
            if blocked_reason
            else "failed"
        )
        return MethodAttempt(
            method="mobile_browser",
            status=status,
            latency_ms=int((time.perf_counter() - started) * 1000),
            products_found=len(products),
            fields_completeness=_extract_field_counts(products),
            products=products,
            http_status=last_status,
            response_size=sum(len(item) for item in page_html.values()) or None,
            error=blocked_reason,
            notes=(
                "Playwright mobile scan completed."
                if products
                else "Playwright did not produce parsable products."
            ),
            diagnostics=diagnostics,
        )

    def _load_demo_cache_products(self, query: str) -> tuple[list[ParsedProduct], str | None]:
        if not self.demo_fallback_enabled:
            return [], None
        if not self.demo_cache_path.exists():
            return [], None
        payload = json.loads(self.demo_cache_path.read_text())
        raw_products = payload.get("products", [])
        cached_at = payload.get("cached_at")
        tokens = {token.lower() for token in query.split() if len(token) >= 2}
        scored: list[tuple[int, ParsedProduct]] = []
        for raw in raw_products:
            product = ParsedProduct(**raw)
            haystack = " ".join(
                [
                    product.title,
                    product.description,
                    " ".join(product.characteristics.values()),
                    product.product_url,
                ]
            ).lower()
            score = sum(1 for token in tokens if token in haystack)
            if tokens and score == 0:
                continue
            scored.append((score, product))
        scored.sort(key=lambda item: (-item[0], item[1].price or 0, item[1].title))
        return [item[1] for item in scored[: self.max_results]], cached_at

    async def search(self, query: str, *, use_cache: bool = True) -> SearchResult:
        normalized = _normalize_ws(query)
        if use_cache:
            cached = self._load_search_cache(normalized)
            if cached is not None:
                return cached

        started = time.perf_counter()
        attempts: list[MethodAttempt] = []

        html_attempt = await self._search_mobile_html(normalized)
        attempts.append(html_attempt)
        if html_attempt.products:
            result = SearchResult(
                query=normalized,
                status=html_attempt.status,
                method_used=html_attempt.method,
                products=html_attempt.products[: self.max_results],
                attempts=attempts,
                blocked_reason=html_attempt.error,
                cached_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
            if use_cache:
                self._store_search_cache(result)
            return result

        browser_attempt = await self._search_mobile_browser(normalized)
        attempts.append(browser_attempt)
        if browser_attempt.products:
            result = SearchResult(
                query=normalized,
                status=browser_attempt.status,
                method_used=browser_attempt.method,
                products=browser_attempt.products[: self.max_results],
                attempts=attempts,
                blocked_reason=browser_attempt.error or html_attempt.error,
                cached_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
            if use_cache:
                self._store_search_cache(result)
            return result

        demo_products, cached_at = self._load_demo_cache_products(normalized)
        blocked_reason = browser_attempt.error or html_attempt.error
        if demo_products:
            demo_attempt = MethodAttempt(
                method="demo_cache",
                status="success",
                latency_ms=0,
                products_found=len(demo_products),
                fields_completeness=_extract_field_counts(demo_products),
                products=demo_products,
                notes="Returned local demo cache after live path failed.",
            )
            attempts.append(demo_attempt)
            result = SearchResult(
                query=normalized,
                status="cached",
                method_used="demo_cache",
                products=demo_products,
                attempts=attempts,
                blocked_reason=blocked_reason,
                cached_at=cached_at,
                is_cached=True,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
            if use_cache:
                self._store_search_cache(result)
            return result

        result = SearchResult(
            query=normalized,
            status="blocked" if blocked_reason else "failed",
            method_used=None,
            products=[],
            attempts=attempts,
            blocked_reason=blocked_reason,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        if use_cache:
            self._store_search_cache(result)
        return result

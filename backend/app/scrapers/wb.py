"""Wildberries scraper — low-footprint mode.

One ``search.wb.ru`` request per cache miss. Images are built from the volume
hint table (no CDN HEAD probes). Card enrichment and Playwright are disabled to
avoid burning the egress IP.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass

from curl_cffi import requests as curl_requests

from app.core.cache import cache_get, cache_set
from app.core.config import settings
from app.core.models import Product, SearchRequest
from app.core.regions import resolve_region
from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://search.wb.ru/exactmatch/ru/common/v4/search"
BASKET_HOST_FMT = "https://basket-{host:02d}.wbbasket.ru"
PRODUCT_URL_FMT = "https://www.wildberries.ru/catalog/{nm}/detail.aspx"

BROWSER_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "x-userid": "0",
}

MAX_RESULTS = 30
_BASKET_MIN, _BASKET_MAX = 1, 50

_HOST_HINT_RANGES: list[tuple[int, int]] = [
    (143, 1), (287, 2), (431, 3), (719, 4), (1007, 5), (1061, 6), (1115, 7),
    (1169, 8), (1313, 9), (1601, 10), (1655, 11), (1919, 12), (2045, 13),
    (2189, 14), (2405, 15), (2621, 16), (2837, 17), (3053, 18), (3269, 19),
    (3485, 20), (3701, 21), (3917, 22), (4193, 23), (4469, 24), (4877, 25),
    (5285, 26), (5693, 27), (6101, 28), (6509, 29), (6917, 30), (7325, 31),
    (7733, 32), (8141, 33), (8549, 34), (8957, 35),
]

_session: curl_requests.Session | None = None
_rate_lock = asyncio.Lock()
_last_wb_request_at = 0.0
_circuit_open_until = 0.0


@dataclass
class _SearchResponse:
    products: list[dict]
    status_code: int
    pow_header: str | None = None
    error: str | None = None


def _get_session() -> curl_requests.Session:
    global _session
    if _session is None:
        _session = curl_requests.Session(impersonate="chrome120")
    return _session


def _reset_session() -> None:
    global _session
    _session = None


def reset_session_for_tests() -> None:
    global _last_wb_request_at, _circuit_open_until
    _reset_session()
    _last_wb_request_at = 0.0
    _circuit_open_until = 0.0


def _circuit_is_open() -> bool:
    return time.monotonic() < _circuit_open_until


def _trip_circuit() -> None:
    global _circuit_open_until
    _circuit_open_until = time.monotonic() + settings.wb_circuit_breaker_seconds
    logger.error(
        "WB circuit breaker open for %ss after block response",
        settings.wb_circuit_breaker_seconds,
    )


async def _throttle_wb() -> None:
    global _last_wb_request_at
    async with _rate_lock:
        interval = settings.wb_min_request_interval_seconds
        jitter = random.uniform(0, interval * 0.2)
        wait = interval + jitter - (time.monotonic() - _last_wb_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_wb_request_at = time.monotonic()


def _cache_key(region: str, query: str) -> str:
    return f"wb:search:{region}:{query.strip().lower()}"


def _price_kopecks(product: dict) -> int:
    sizes = product.get("sizes") or []
    if sizes:
        price = (sizes[0] or {}).get("price") or {}
        kopecks = price.get("product") or price.get("total") or price.get("basic")
        if kopecks:
            return int(kopecks)
    legacy = product.get("salePriceU") or product.get("priceU")
    return int(legacy) if legacy else 0


def _host_hint(vol: int) -> int:
    for max_vol, host in _HOST_HINT_RANGES:
        if vol <= max_vol:
            return host
    return _HOST_HINT_RANGES[-1][1] + 1


def _host_for_nm(nm: int) -> int:
    vol = nm // 100000
    return max(_BASKET_MIN, min(_host_hint(vol), _BASKET_MAX))


def _image_url(host: int, nm: int) -> str:
    vol, part = nm // 100000, nm // 1000
    return f"{BASKET_HOST_FMT.format(host=host)}/vol{vol}/part{part}/{nm}/images/big/1.webp"


def _http_error_message(status_code: int, body: str) -> str:
    if status_code == 429:
        return (
            "HTTP 429: антибот Wildberries (rate-limit или IP). "
            "Подождите или используйте российский IP без VPN."
        )
    if status_code == 498:
        return "HTTP 498: домашний антибот Wildberries заблокировал IP."
    snippet = body.strip().replace("\n", " ")[:120]
    return f"HTTP {status_code}: {snippet or 'пустой ответ'}"


def _log_search_diagnosis(pow_header: str | None, products: list[dict], query: object) -> None:
    pow_header = pow_header or ""
    if products:
        if "status=invalid" in pow_header:
            logger.info(
                "WB search OK: %d products for %r (PoW header present, results served anyway)",
                len(products),
                query,
            )
        return
    if "status=invalid" in pow_header:
        logger.error(
            "WB search returned 0 products for %r with PoW challenge (x-pow=%s...)",
            query,
            pow_header[:80],
        )
    else:
        logger.warning("WB search returned 0 products for %r with HTTP 200", query)


def _fetch_search_sync(params: dict[str, object]) -> _SearchResponse:
    query = params.get("query")
    headers = {
        **BROWSER_HEADERS,
        "x-queryid": f"qid{int(time.time() * 1000)}",
    }

    last_block: _SearchResponse | None = None
    for attempt in range(2):
        try:
            response = _get_session().get(
                SEARCH_URL,
                params=params,
                headers=headers,
                timeout=settings.scraper_timeout_seconds,
            )
        except curl_requests.RequestsError as exc:
            logger.error("WB search network error for %r: %r", query, exc)
            return _SearchResponse([], status_code=0, error=f"Сеть: {exc}")

        pow_header = response.headers.get("x-pow") or response.headers.get("X-Pow")
        if response.status_code in {429, 498}:
            last_block = _SearchResponse(
                [],
                status_code=response.status_code,
                pow_header=pow_header,
                error=_http_error_message(response.status_code, response.text),
            )
            logger.warning(
                "WB search blocked for %r: HTTP %s (attempt %s/2)",
                query,
                response.status_code,
                attempt + 1,
            )
            _reset_session()
            if attempt == 0:
                time.sleep(0.5)
                headers["x-queryid"] = f"qid{int(time.time() * 1000)}"
                continue
            _trip_circuit()
            return last_block

        if response.status_code != 200:
            logger.error("WB search FAILED for %r: HTTP %s", query, response.status_code)
            return _SearchResponse(
                [],
                status_code=response.status_code,
                pow_header=pow_header,
                error=_http_error_message(response.status_code, response.text),
            )

        try:
            payload = response.json()
        except ValueError as exc:
            logger.error("WB search non-JSON body for %r: %s", query, exc)
            return _SearchResponse(
                [],
                status_code=response.status_code,
                pow_header=pow_header,
                error="Wildberries вернул не-JSON ответ",
            )

        products = (payload.get("products") or [])[:MAX_RESULTS]
        _log_search_diagnosis(pow_header, products, query)
        if products:
            return _SearchResponse(products, status_code=response.status_code, pow_header=pow_header)

        return _SearchResponse(
            [],
            status_code=response.status_code,
            pow_header=pow_header,
            error="Wildberries вернул пустой каталог",
        )

    return last_block or _SearchResponse([], status_code=429, error=_http_error_message(429, ""))


def _base_characteristics(product: dict) -> dict[str, str]:
    chars: dict[str, str] = {}
    if product.get("brand"):
        chars["Бренд"] = str(product["brand"])
    if product.get("supplier"):
        chars["Продавец"] = str(product["supplier"])
    return chars


def _build_product(raw: dict, image_url: str, characteristics: dict[str, str]) -> Product | None:
    nm = raw.get("id")
    name = raw.get("name")
    price = _price_kopecks(raw)
    if not nm or not name or price <= 0:
        return None

    feedbacks = raw.get("nmFeedbacks") or raw.get("feedbacks")
    rating = raw.get("reviewRating") or raw.get("nmReviewRating") or raw.get("rating")
    return Product(
        source="wildberries",
        source_domain="wildberries.ru",
        title=str(name),
        price=price,
        image_url=image_url,
        product_url=PRODUCT_URL_FMT.format(nm=nm),
        characteristics=characteristics,
        rating=float(rating) if rating else None,
        reviews_count=int(feedbacks) if feedbacks else None,
    )


def _assemble_products(raw_products: list[dict]) -> list[Product]:
    products: list[Product] = []
    for raw in raw_products:
        nm = raw.get("id")
        if not nm or not raw.get("name") or _price_kopecks(raw) <= 0:
            continue
        host = _host_for_nm(int(nm))
        product = _build_product(
            raw,
            _image_url(host, int(nm)),
            _base_characteristics(raw),
        )
        if product is not None:
            products.append(product)
    return products


async def _load_cached_products(region: str, query: str) -> list[Product] | None:
    if not settings.wb_cache_enabled:
        return None
    cached = await asyncio.to_thread(cache_get, _cache_key(region, query))
    if cached is None:
        return None
    logger.info("WB cache hit for query=%r region=%r", query, region)
    return [Product.model_validate(item) for item in cached]


async def _store_cached_products(region: str, query: str, products: list[Product]) -> None:
    if not settings.wb_cache_enabled or not products:
        return
    payload = [product.model_dump(mode="json") for product in products]
    await asyncio.to_thread(cache_set, _cache_key(region, query), payload)


class WildberriesScraper(BaseScraper):
    source = "wildberries"

    async def search(self, request: SearchRequest) -> list[Product]:
        self.clear_error()
        region = resolve_region(request.region)
        query = request.query.strip()
        if not query:
            return []

        cached = await _load_cached_products(region.id, query)
        if cached is not None:
            return cached

        if _circuit_is_open():
            self.set_error(
                "Wildberries временно недоступен (слишком много блокировок). "
                f"Повторите через {int(settings.wb_circuit_breaker_seconds // 60)} мин."
            )
            return []

        params = {
            "query": query,
            "resultset": "catalog",
            "dest": region.wb_dest,
            "curr": "rub",
            "lang": "ru",
            "appType": 1,
            "page": 1,
        }

        await _throttle_wb()
        attempt = await asyncio.to_thread(_fetch_search_sync, params)
        if attempt.error:
            self.set_error(attempt.error)
            logger.warning("WB scraper failed for query=%r: %s", query, attempt.error)
            return []

        products = _assemble_products(attempt.products)
        if not products:
            self.set_error("Wildberries вернул товары, но ни один не прошёл фильтрацию (цена/поля)")
            return []

        await _store_cached_products(region.id, query, products)

        usable = sum(
            1 for raw in attempt.products if raw.get("id") and raw.get("name") and _price_kopecks(raw) > 0
        )
        logger.info(
            "WB scraper funnel for %r: %d raw -> %d usable -> %d returned (1 HTTP request)",
            query,
            len(attempt.products),
            usable,
            len(products),
        )
        return products


scraper = WildberriesScraper()

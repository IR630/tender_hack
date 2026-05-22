"""Wildberries scraper.

Strategy (see docs/architecture and live findings):
- Search via the public ``search.wb.ru`` JSON API. We use the **v4** endpoint
  on purpose: newer versions (v9) enforce a proof-of-work challenge
  (``x-pow`` header) and truncate the body, while v4 still serves full results
  as long as realistic browser headers are present. This is our justified
  rate-limit / anti-bot workaround; a PoW solver is the documented fallback if
  v4 is ever closed.
- Prices live in ``sizes[0].price.product`` (kopecks). Images and full
  characteristics live on the ``basket-NN.wbbasket.ru`` CDN, where the host
  number is not a stable formula, so we resolve it by probing (cheap HEAD,
  memoized per volume).
- Characteristics (an extra request per item) are fetched only for the top-K
  results, which the search API already returns in relevance order.
"""

import asyncio
import logging

import httpx

from app.core.config import settings
from app.core.models import Product, SearchRequest
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
}

# WB region geo-id (``dest``). Default = Moscow; extend as needed.
REGION_DEST = {
    "moscow": -1257786,
    "москва": -1257786,
}
DEFAULT_DEST = -1257786

# How many products to return, and how many of them to enrich with full
# characteristics. Both bounded to keep latency and request volume in check.
MAX_RESULTS = 30
ENRICH_TOP_K = 12

# Concurrency cap for CDN probes / card.json fetches.
_MAX_CONCURRENCY = 10

# basket host probe bounds (basket-01 .. basket-50 currently exist).
_BASKET_MIN, _BASKET_MAX = 1, 50

# Hint table: upper-bound volume (inclusive) -> basket host. Accurate for
# low/mid volumes; the probe corrects stale high-end entries. Used only to
# start the probe near the right host. Volume = nm // 100000.
_HOST_HINT_RANGES: list[tuple[int, int]] = [
    (143, 1), (287, 2), (431, 3), (719, 4), (1007, 5), (1061, 6), (1115, 7),
    (1169, 8), (1313, 9), (1601, 10), (1655, 11), (1919, 12), (2045, 13),
    (2189, 14), (2405, 15), (2621, 16), (2837, 17), (3053, 18), (3269, 19),
    (3485, 20), (3701, 21), (3917, 22), (4193, 23), (4469, 24), (4877, 25),
    (5285, 26), (5693, 27), (6101, 28), (6509, 29), (6917, 30), (7325, 31),
    (7733, 32), (8141, 33), (8549, 34), (8957, 35),
]

# vol -> resolved host (or None if no host serves it). Process-wide memo.
_basket_memo: dict[int, int | None] = {}


def _dest_for(region: str | None) -> int:
    if not region:
        return DEFAULT_DEST
    return REGION_DEST.get(region.strip().lower(), DEFAULT_DEST)


def _price_rub(product: dict) -> int:
    """Sale price in whole rubles, or 0 if unavailable."""
    sizes = product.get("sizes") or []
    if sizes:
        price = (sizes[0] or {}).get("price") or {}
        kopecks = price.get("product") or price.get("total") or price.get("basic")
        if kopecks:
            return int(kopecks) // 100
    # Legacy fallback (older API shapes).
    legacy = product.get("salePriceU") or product.get("priceU")
    return int(legacy) // 100 if legacy else 0


def _host_hint(vol: int) -> int:
    for max_vol, host in _HOST_HINT_RANGES:
        if vol <= max_vol:
            return host
    return _HOST_HINT_RANGES[-1][1] + 1


def _probe_order(vol: int) -> list[int]:
    """Hosts to probe, starting at the hint and expanding outward."""
    hint = max(_BASKET_MIN, min(_host_hint(vol), _BASKET_MAX))
    order, seen = [], set()
    for radius in range(_BASKET_MAX - _BASKET_MIN + 1):
        for host in (hint + radius, hint - radius):
            if _BASKET_MIN <= host <= _BASKET_MAX and host not in seen:
                seen.add(host)
                order.append(host)
    return order


async def _resolve_host(client: httpx.AsyncClient, nm: int) -> int | None:
    """Find the basket host serving ``nm``'s media, memoized per volume."""
    vol = nm // 100000
    if vol in _basket_memo:
        return _basket_memo[vol]

    part = nm // 1000
    for host in _probe_order(vol):
        url = f"{BASKET_HOST_FMT.format(host=host)}/vol{vol}/part{part}/{nm}/images/big/1.webp"
        try:
            resp = await client.head(url)
        except httpx.HTTPError:
            continue
        if resp.status_code == 200:
            _basket_memo[vol] = host
            return host
    _basket_memo[vol] = None
    return None


def _image_url(host: int, nm: int) -> str:
    vol, part = nm // 100000, nm // 1000
    return f"{BASKET_HOST_FMT.format(host=host)}/vol{vol}/part{part}/{nm}/images/big/1.webp"


def _base_characteristics(product: dict) -> dict[str, str]:
    chars: dict[str, str] = {}
    if product.get("brand"):
        chars["Бренд"] = str(product["brand"])
    if product.get("supplier"):
        chars["Продавец"] = str(product["supplier"])
    return chars


async def _fetch_card_characteristics(
    client: httpx.AsyncClient, host: int, nm: int
) -> dict[str, str]:
    """Pull the full name/value characteristics from the basket card.json."""
    vol, part = nm // 100000, nm // 1000
    url = f"{BASKET_HOST_FMT.format(host=host)}/vol{vol}/part{part}/{nm}/info/ru/card.json"
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        card = resp.json()
    except (httpx.HTTPError, ValueError):
        return {}

    chars: dict[str, str] = {}
    if card.get("subj_name"):
        chars["Категория"] = str(card["subj_name"])
    option_groups = [card.get("options") or []]
    option_groups += [g.get("options") or [] for g in (card.get("grouped_options") or [])]
    for options in option_groups:
        for opt in options:
            name, value = opt.get("name"), opt.get("value")
            if name and value:
                chars[str(name)] = str(value)
    return chars


def _build_product(raw: dict, image_url: str, characteristics: dict[str, str]) -> Product | None:
    nm = raw.get("id")
    name = raw.get("name")
    price = _price_rub(raw)
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


class WildberriesScraper(BaseScraper):
    source = "wildberries"

    async def _fetch_search(self, client: httpx.AsyncClient, params: dict) -> list[dict]:
        """Call the search API, with one short retry on a 429 soft-block.

        Returns ``[]`` on any transient failure (rate limit, timeout, network,
        bad JSON) so the orchestrator degrades gracefully instead of failing.
        Persistent rate limits are an infra concern (caching / proxies), not
        something to burn the request budget retrying.
        """
        for attempt in range(2):
            try:
                resp = await client.get(SEARCH_URL, params=params)
                resp.raise_for_status()
                return (resp.json().get("products") or [])[:MAX_RESULTS]
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429 and attempt == 0:
                    logger.warning("WB search rate-limited (429), retrying once")
                    await asyncio.sleep(0.7)
                    continue
                logger.warning("WB search failed: %s", exc)
                return []
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("WB search failed: %s", exc)
                return []
        return []

    async def search(self, request: SearchRequest) -> list[Product]:
        params = {
            "query": request.query,
            "resultset": "catalog",
            "dest": _dest_for(request.region),
            "curr": "rub",
            "lang": "ru",
            "appType": 1,
            "page": 1,
        }
        timeout = httpx.Timeout(settings.scraper_timeout_seconds)
        async with httpx.AsyncClient(
            headers=BROWSER_HEADERS, timeout=timeout, follow_redirects=True
        ) as client:
            raw_products = await self._fetch_search(client, params)
            if not raw_products:
                return []

            sem = asyncio.Semaphore(_MAX_CONCURRENCY)

            async def assemble(index: int, raw: dict) -> Product | None:
                nm = raw.get("id")
                # Skip media work for items that won't survive _build_product
                # anyway (no id / name / price) — saves CDN requests.
                if not nm or not raw.get("name") or _price_rub(raw) <= 0:
                    return None
                async with sem:
                    host = await _resolve_host(client, nm)
                    image_url = _image_url(host, nm) if host is not None else ""
                    chars = _base_characteristics(raw)
                    if host is not None and index < ENRICH_TOP_K:
                        chars.update(await _fetch_card_characteristics(client, host, nm))
                return _build_product(raw, image_url, chars)

            results = await asyncio.gather(
                *(assemble(i, raw) for i, raw in enumerate(raw_products))
            )

        products = [p for p in results if p is not None]
        logger.info("WB scraper: %d products for query %r", len(products), request.query)
        return products


scraper = WildberriesScraper()

"""URL quality heuristics for live web discovery (product vs catalog/compare/news)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Shops that block plain HTTP clients (401/403) — deprioritize in ranking
_FETCH_BLOCKED_HOSTS = frozenset({"dns-shop.ru", "citilink.ru", "cifrus.ru"})

# Hard reject: comparison, news, review aggregators, foreign shopping locales
_REJECT_HOSTS = (
    "gsmarena.com",
    "nanoreview.net",
    "phonemore.com",
    "lenta.ru",
    "chip.de",
    "idealo.de",
    "mediamarkt.de",
    "bild.de",
    "apple.com",
)

_REJECT_PATH_RE = re.compile(
    r"(?:"
    r"/compare(?:/|\?|$)"
    r"|compare\.php"
    r"|/filter/"
    r"|/f/"
    r"|/news/"
    r"|/artikel/"
    r"|/brand/"
    r"|/articles?/"
    r"|/blog/"
    r"|/responses/"
    r"|/customers/products/"
    r")",
    re.IGNORECASE,
)

_FOREIGN_LOCALE_RE = re.compile(
    r"(?:"
    r"\.de(?:/|$)"
    r"|\.com/(?:de|sg|uk|us|au|fr|it|es)(?:/|$)"
    r"|/de/"
    r"|/sg/"
    r")",
    re.IGNORECASE,
)

_PRODUCT_PATH_RE = re.compile(
    r"(?:"
    r"/products?/"
    r"|/p/\d"
    r"|/item/"
    r"|/goods/"
    r"|/tovar/"
    r"|/card/"
    r"|/(?:shop/)?details/"
    r"|/catalog/(?:item|detail)/"
    r"|/catalog_shin/"
    r"|/razmer/"
    r"|/\d{6,}"
    r"|/\d{3}-\d{2}-\d{2}/?"
    r"|[_-]shina[_-]"
    r")",
    re.IGNORECASE,
)

_CATALOG_PATH_RE = re.compile(
    r"(?:"
    r"/catalog/"
    r"|/category/"
    r"|/categories/"
    r"|/smartfony/"
    r"|/collection/"
    r")",
    re.IGNORECASE,
)

_TIRE_SIZE_RE = re.compile(r"\d{3}[-/]\d{2}[-/]R?\d{2}", re.IGNORECASE)

_LISTING_SLUGS = frozenset(
    {
        "apple-iphone",
        "apple_iphone",
        "catalog.html",
        "iphone",
        "iphone-15",
        "iphone-16",
        "iphone-se",
        "klaviatury",
        "monitory",
        "naushniki",
        "noutbuki",
        "planshety",
        "printery",
        "shiny",
        "smartfony",
        "tyre",
        "tyres",
    }
)
_LISTING_PREFIXES = (
    "brand_",
    "category_",
    "klaviatury",
    "myshi",
    "mysi",
    "printery",
)
_MODEL_FAMILY_RE = re.compile(
    r"^(?:apple[-_])?iphone(?:[-_]\d{1,2})?(?:[-_](?:se|pro|max|plus|mini))*$",
    re.IGNORECASE,
)
_PRODUCT_DETAIL_SLUG_RE = re.compile(
    r"(?:"
    r"\d{5,}"
    r"|\d{2,4}(?:gb|tb)"
    r"|(?:gb|tb)[-_]?\d{2,4}"
    r"|black|white|blue|green|red|pink|gray|grey|silver|gold|purple"
    r"|titan|natural|midnight|starlight"
    r")",
    re.IGNORECASE,
)


def _host(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_rejected_url(url: str) -> bool:
    """True when URL is clearly not a product page worth fetching."""
    host = _host(url)
    if any(host == h or host.endswith("." + h) for h in _REJECT_HOSTS):
        return True
    if _REJECT_PATH_RE.search(urlparse(url).path + urlparse(url).query):
        return True
    if _FOREIGN_LOCALE_RE.search(url):
        return True
    return False


def is_fetch_blocked(url: str) -> bool:
    """Hosts that block plain HTTP clients (401/403). Still valid product pages,
    but the fetcher should expect failure / use a stealth path."""
    return _host(url) in _FETCH_BLOCKED_HOSTS


def is_ru_domain(url: str) -> bool:
    host = _host(url)
    return host.endswith(".ru") or host.endswith(".рф")


def _path_segments(path: str) -> list[str]:
    return [part for part in path.split("/") if part]


def _looks_like_listing_slug(slug: str) -> bool:
    lowered = slug.lower().replace("_", "-")
    return (
        slug.lower() in _LISTING_SLUGS
        or lowered in _LISTING_SLUGS
        or slug.lower().startswith(_LISTING_PREFIXES)
        or bool(_MODEL_FAMILY_RE.match(lowered))
    )


def _catalog_slug_is_product(slug: str) -> bool:
    lowered = slug.lower()
    if _looks_like_listing_slug(lowered):
        return False
    if lowered.isdigit():
        return len(lowered) >= 5
    if _PRODUCT_DETAIL_SLUG_RE.search(lowered):
        return True
    return False


def looks_like_product_url(url: str) -> bool:
    """True when the path is a concrete product URL, not a catalog family page."""
    path = urlparse(url).path.lower()
    if _PRODUCT_PATH_RE.search(path):
        return True
    if _TIRE_SIZE_RE.search(path):
        return True
    segments = _path_segments(path)
    if not segments:
        return False
    if segments[-1].isdigit():
        if "catalog" in segments and len(segments[-1]) < 5:
            return False
        return True
    if "product" in segments:
        return True
    if "catalog" in segments and len(segments) == 2:
        slug = segments[-1].lower()
        return _catalog_slug_is_product(slug)
    return False


def looks_like_listing_url(url: str) -> bool:
    """True for catalog/listing/search pages that can be expanded into products."""
    if is_rejected_url(url) or looks_like_product_url(url):
        return False
    path = urlparse(url).path.lower()
    segments = _path_segments(path)
    if not segments:
        return True
    if _CATALOG_PATH_RE.search(path):
        return True
    if any(_looks_like_listing_slug(segment) for segment in segments):
        return True
    return False


def url_quality_score(url: str) -> float:
    """Higher = more likely a purchasable product page. -1 = reject."""
    if is_rejected_url(url):
        return -1.0
    path = urlparse(url).path
    has_product = looks_like_product_url(url)
    has_catalog = looks_like_listing_url(url) or bool(_CATALOG_PATH_RE.search(path))
    if has_catalog and not has_product:
        return -1.0
    score = 0.2
    if is_ru_domain(url):
        score += 0.35
    if has_product:
        score += 0.4
    if path.count("/") <= 3 and not has_product:
        score -= 0.15
    if _host(url) in _FETCH_BLOCKED_HOSTS:
        score -= 0.5
    return score


def filter_and_sort_candidates(candidates: list) -> list:
    """Drop rejected URLs; prefer .ru product pages when available."""
    if not candidates:
        return []
    scored = [(c, url_quality_score(c.url)) for c in candidates]
    viable = [(c, s) for c, s in scored if s >= 0]
    if not viable:
        soft = [c for c, s in scored if not is_rejected_url(c.url)]
        if not soft:
            return []
        viable = [(c, url_quality_score(c.url)) for c in soft]
        viable = [(c, max(s, 0)) for c, s in viable]

    ru_viable = [(c, s) for c, s in viable if is_ru_domain(c.url)]
    pool = ru_viable if ru_viable else viable
    pool.sort(key=lambda item: item[1], reverse=True)
    return [c for c, _ in pool]

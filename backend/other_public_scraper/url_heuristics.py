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
    r"/product/"
    r"|/products?/"
    r"|/p/\d"
    r"|/item/"
    r"|/goods/"
    r"|/tyre[s]?/"
    r"|/shina/"
    r"|/catalog/\d+"
    r"|/\d{6,}"
    r"|/\d{3}-\d{2}-\d{2}/?"
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


def url_quality_score(url: str) -> float:
    """Higher = more likely a purchasable product page. -1 = reject."""
    if is_rejected_url(url):
        return -1.0
    path = urlparse(url).path
    has_product = bool(_PRODUCT_PATH_RE.search(url))
    has_catalog = bool(_CATALOG_PATH_RE.search(path))
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

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from other_public_scraper.models import OtherExtractResult

ApiSearch = Callable[[str, str, int], Awaitable[list[OtherExtractResult]]]


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


@dataclass(frozen=True, slots=True)
class DomainStrategy:
    name: str
    domains: tuple[str, ...]
    categories: tuple[str, ...] = ()
    canonical_group: str | None = None
    has_listing_adapter: bool = False
    has_challenge_solver: bool = False
    api_search: ApiSearch | None = None

    def supports_domain(self, domain: str) -> bool:
        return any(domain == item or domain.endswith("." + item) for item in self.domains)

    def supports_url(self, url: str) -> bool:
        return self.supports_domain(_domain(url))

    def supports_category(self, category: str) -> bool:
        return not self.categories or category in self.categories

    def listing_key(self, url: str) -> str:
        return self.canonical_group or _domain(url)


async def _search_mvideo(query: str, region_id: str, limit: int) -> list[OtherExtractResult]:
    from other_public_scraper.pipelines.mvideo_api import search_mvideo_products

    return await search_mvideo_products(query, region_id, limit=limit)


DOMAIN_STRATEGIES: tuple[DomainStrategy, ...] = (
    DomainStrategy(
        name="e2e4",
        domains=("e2e4online.ru",),
        categories=("orgtech",),
        canonical_group="e2e4online.ru",
        has_listing_adapter=True,
    ),
    DomainStrategy(
        name="citilink",
        domains=("citilink.ru",),
        categories=("orgtech",),
        has_listing_adapter=True,
        has_challenge_solver=True,
    ),
    DomainStrategy(
        name="mvideo",
        domains=("mvideo.ru",),
        categories=("orgtech",),
        has_listing_adapter=True,
        api_search=_search_mvideo,
    ),
    DomainStrategy(
        name="dns-shop",
        domains=("dns-shop.ru",),
        categories=("orgtech",),
        has_listing_adapter=True,
        has_challenge_solver=True,
    ),
    DomainStrategy(
        name="technocity",
        domains=("technocity.ru",),
        categories=("orgtech",),
        has_listing_adapter=True,
    ),
    DomainStrategy(
        name="4tochki",
        domains=("4tochki.ru",),
        categories=("tires",),
        has_listing_adapter=True,
    ),
    DomainStrategy(
        name="koleso",
        domains=("koleso.ru",),
        categories=("tires",),
        has_listing_adapter=True,
    ),
    DomainStrategy(
        name="lamoda",
        domains=("lamoda.ru",),
        categories=("clothes",),
        has_listing_adapter=True,
    ),
)


def strategy_for_url(url: str) -> DomainStrategy | None:
    domain = _domain(url)
    for strategy in DOMAIN_STRATEGIES:
        if strategy.supports_domain(domain):
            return strategy
    return None


def listing_domain_key(url: str) -> str:
    strategy = strategy_for_url(url)
    if strategy is not None:
        return strategy.listing_key(url)
    return _domain(url)


async def search_api_products(
    query: str,
    region_id: str,
    category: str,
    *,
    limit: int,
) -> list[OtherExtractResult]:
    products: list[OtherExtractResult] = []
    for strategy in DOMAIN_STRATEGIES:
        if strategy.api_search is None or not strategy.supports_category(category):
            continue
        products.extend(await strategy.api_search(query, region_id, limit))
        if len(products) >= limit:
            break
    return products[:limit]

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class ScraperErrorType(str, Enum):
    NETWORK = "network"
    TIMEOUT = "timeout"
    INDEX_EMPTY = "index_empty"
    ALL_SOURCES_FAILED = "all_sources_failed"
    SITEMAP_BLOCKED = "sitemap_blocked"


class ScraperError(Exception):
    def __init__(self, message: str, error_type: ScraperErrorType) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type


class ProductUrl(BaseModel):
    numeric_id: str
    slug: str
    url: HttpUrl
    category: str | None = None


class RawOgData(BaseModel):
    title: str | None = None
    image_url: str | None = None
    description: str | None = None
    price_rub: int | None = None
    currency: str = "RUB"
    availability: str | None = None
    canonical_url: str | None = None
    fields_extracted: list[str] = Field(default_factory=list)
    fields_missing: list[str] = Field(default_factory=list)


class ProductResult(BaseModel):
    title: str
    price_rub: int | None = None
    image_url: HttpUrl | None = None
    product_url: HttpUrl
    description: str | None = None
    characteristics: dict[str, str] = Field(default_factory=dict)
    incomplete: bool = False
    source: str = "meilisearch"  # meilisearch | searxng | cache

    @property
    def has_price(self) -> bool:
        return self.price_rub is not None and self.price_rub > 0


class SearchMetrics(BaseModel):
    meili_count: int = 0
    searxng_count: int = 0
    cache_count: int = 0
    items_incomplete: int = 0

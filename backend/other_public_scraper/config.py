from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DOMAIN_BLACKLIST = {
    "wildberries.ru",
    "wb.ru",
    "ozon.ru",
    "market.yandex.ru",
    "avito.ru",
    "youla.ru",
    "kazanexpress.ru",
    "aliexpress.ru",
    "aliexpress.com",
    "price.ru",
    "e-katalog.ru",
    "market.ru",
    "vc.ru",
    "habr.com",
    "dtf.ru",
    "pikabu.ru",
    "duckduckgo.com",
    "kp.ru",
    "mail.ru",
    "hi-tech.mail.ru",
    "expertcen.ru",
    "ratingpc.ru",
    "ixbt.com",
    "3dnews.ru",
    "wikipedia.org",
    "youtube.com",
    "farpost.ru",
    "drom.ru",
    "baza.drom.ru",
}

PRECRAWL_DOMAINS = (
    "dns-shop.ru",
    "citilink.ru",
    "mvideo.ru",
    "4tochki.ru",
    "koleso.ru",
    "lamoda.ru",
)

CATEGORY_PROTOTYPES = {
    "orgtech": "ноутбук компьютер принтер монитор клавиатура мышь процессор",
    "tires": "шина резина колесо диск типоразмер летняя зимняя",
    "clothes": "одежда куртка платье ботинки пальто джинсы футболка",
}

ORGTECH_BRANDS = (
    "canon",
    "hp",
    "epson",
    "logitech",
    "acer",
    "lenovo",
    "asus",
    "dell",
    "brother",
    "samsung",
)

CLOTHES_NEGATIVE = ("чехол", "кейс", "пленка", "плёнка", "аксессуар", "стекло")

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class OtherPublicSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    searxng_url: str = Field(default="http://localhost:8080", validation_alias="SEARXNG_URL")
    meilisearch_url: str = Field(default="http://localhost:7700", validation_alias="MEILI_URL")
    meilisearch_api_key: str = Field(default="", validation_alias="MEILI_MASTER_KEY")
    meilisearch_index: str = Field(default="other_products", validation_alias="OTHER_MEILI_INDEX")
    other_search_timeout_seconds: float = Field(
        default=45.0, validation_alias="OTHER_SEARCH_TIMEOUT_SECONDS"
    )
    other_fetch_concurrency: int = Field(default=4, validation_alias="OTHER_FETCH_CONCURRENCY")
    other_searxng_cache_ttl: int = Field(default=1800, validation_alias="OTHER_SEARXNG_CACHE_TTL")
    other_cache_enabled: bool = Field(default=False, validation_alias="OTHER_CACHE_ENABLED")
    other_precrawl_domains: str = Field(
        default=",".join(PRECRAWL_DOMAINS), validation_alias="OTHER_PRECRAWL_DOMAINS"
    )
    other_precrawl_max_per_domain: int = Field(
        default=250, validation_alias="OTHER_PRECRAWL_MAX_PER_DOMAIN"
    )
    other_llm_enabled: bool = Field(default=False, validation_alias="OTHER_LLM_ENABLED")
    other_meili_read_enabled: bool = Field(default=False, validation_alias="OTHER_MEILI_READ_ENABLED")
    other_ddg_enabled: bool = Field(default=True, validation_alias="OTHER_DDG_ENABLED")
    other_ddg_timeout_seconds: float = Field(default=4.0, validation_alias="OTHER_DDG_TIMEOUT_SECONDS")
    other_yahoo_enabled: bool = Field(default=True, validation_alias="OTHER_YAHOO_ENABLED")
    other_yahoo_timeout_seconds: float = Field(default=8.0, validation_alias="OTHER_YAHOO_TIMEOUT_SECONDS")
    other_bing_fallback_enabled: bool = Field(default=False, validation_alias="OTHER_BING_FALLBACK_ENABLED")
    other_bing_timeout_seconds: float = Field(default=4.0, validation_alias="OTHER_BING_TIMEOUT_SECONDS")
    other_catalog_harvest_per_listing: int = Field(
        default=8, validation_alias="OTHER_CATALOG_HARVEST_PER_LISTING"
    )
    other_catalog_harvest_depth: int = Field(default=2, validation_alias="OTHER_CATALOG_HARVEST_DEPTH")
    other_catalog_harvest_max_listings: int = Field(
        default=4, validation_alias="OTHER_CATALOG_HARVEST_MAX_LISTINGS"
    )
    other_catalog_harvest_budget_seconds: float = Field(
        default=12.0, validation_alias="OTHER_CATALOG_HARVEST_BUDGET_SECONDS"
    )
    other_request_timeout: float = Field(default=10.0, validation_alias="OTHER_REQUEST_TIMEOUT")
    other_snippet_similarity_threshold: float = Field(
        default=0.45, validation_alias="OTHER_SNIPPET_SIMILARITY_THRESHOLD"
    )
    other_title_similarity_threshold: float = Field(
        default=0.40, validation_alias="OTHER_TITLE_SIMILARITY_THRESHOLD"
    )
    other_max_results: int = Field(default=15, validation_alias="OTHER_MAX_RESULTS")
    other_rank_pool_size: int = Field(default=32, validation_alias="OTHER_RANK_POOL_SIZE")
    other_listing_products_per_page: int = Field(
        default=8, validation_alias="OTHER_LISTING_PRODUCTS_PER_PAGE"
    )
    other_max_searxng_urls: int = Field(default=20, validation_alias="OTHER_MAX_SEARXNG_URLS")


settings = OtherPublicSettings()

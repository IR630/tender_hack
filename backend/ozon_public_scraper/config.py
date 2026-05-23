from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Category slug keywords — experimental, logged as category_keyword_assumed
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "clothing": [
        "odezhda",
        "futbolk",
        "krossovk",
        "kurtka",
        "platy",
        "rubashk",
        "dzhins",
        "sviter",
        "bryuk",
        "kostyum",
        "nosk",
        "shapka",
        "perchatk",
    ],
    "tires": [
        "shina",
        "shiny",
        "shin-",
        "avtoshin",
        "pokryshk",
        "disk-",
        "koleso",
    ],
    "office": [
        "printer",
        "mfu",
        "skaner",
        "skanner",
        "orgteh",
        "laserjet",
        "kartrid",
        "bumaga-ofis",
        "proektor",
    ],
}


class OzonPublicSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    searxng_url: str = Field(default="http://localhost:8080", validation_alias="SEARXNG_URL")
    meilisearch_url: str = Field(default="http://localhost:7700", validation_alias="MEILI_URL")
    meilisearch_api_key: str = Field(default="", validation_alias="MEILI_MASTER_KEY")
    meilisearch_index: str = "ozon_products"

    ozon_log_dir: str = Field(default="./logs", validation_alias="OZON_PUBLIC_LOG_DIR")
    ozon_max_concurrent: int = Field(default=2, validation_alias="OZON_MAX_CONCURRENT")
    ozon_request_interval_ms: int = Field(default=500, validation_alias="OZON_REQUEST_INTERVAL_MS")
    ozon_searxng_cache_ttl: int = Field(default=1800, validation_alias="OZON_SEARXNG_CACHE_TTL")
    ozon_og_cache_ttl: int = Field(default=3600, validation_alias="OZON_OG_CACHE_TTL")
    ozon_og_incomplete_cache_ttl: int = Field(
        default=300,
        validation_alias="OZON_OG_INCOMPLETE_CACHE_TTL",
    )
    ozon_blocked_url_ttl: int = Field(default=3600, validation_alias="OZON_BLOCKED_URL_TTL")
    ozon_request_timeout: float = Field(default=15.0, validation_alias="OZON_REQUEST_TIMEOUT")
    ozon_enable_browser_fallback: bool = Field(
        default=False, validation_alias="OZON_ENABLE_BROWSER_FALLBACK"
    )
    ozon_sitemap_pause_seconds: float = Field(default=2.0, validation_alias="OZON_SITEMAP_PAUSE")


settings = OzonPublicSettings()

SITEMAP_INDEX_URL = "https://www.ozon.ru/sitemap.xml"
ROBOTS_URL = "https://www.ozon.ru/robots.txt"
PRODUCT_URL_RE = r"https://www\.ozon\.ru/product/(.+)-(\d+)/?"

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
YANDEXBOT_UA = "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)"
GOOGLEBOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

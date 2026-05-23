from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Tender Hack Price Aggregator"
    debug: bool = False
    redis_url: str = "redis://localhost:6379/0"
    searxng_url: str = "http://localhost:8080"
    cache_ttl_seconds: int = 6 * 60 * 60
    scraper_timeout_seconds: float = 8.0
    wb_min_request_interval_seconds: float = 1.5
    wb_circuit_breaker_seconds: float = 10 * 60
    wb_cache_enabled: bool = True
    ym_cache_enabled: bool = True
    ym_search_max_pages: int = 3
    ozon_use_browser: bool = True
    ozon_browser_wait_seconds: float = 25.0
    ozon_browser_headless: bool | None = None
    ozon_browser_max_results: int = 30
    search_task_poll_interval_seconds: float = 3.0


settings = Settings()

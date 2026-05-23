from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Tender Hack Price Aggregator"
    debug: bool = False
    redis_url: str = "redis://localhost:6379/0"
    searxng_url: str = "http://localhost:8080"
    cache_ttl_seconds: int = 6 * 60 * 60
    scraper_timeout_seconds: float = 8.0
    wb_min_request_interval_seconds: float = 3.0
    wb_circuit_breaker_seconds: float = 5 * 60
    wb_cache_enabled: bool = True
    wb_impersonate: str = "chrome131"
    wb_retry_max_attempts: int = 1
    wb_retry_backoff_base_seconds: float = 5.0
    wb_retry_max_backoff_seconds: float = 10.0
    wb_max_results: int = 5
    wb_proxy: str = ""
    ym_cache_enabled: bool = True
    ym_search_max_pages: int = 3
    ozon_use_browser: bool = True
    ozon_browser_wait_seconds: float = 30.0
    ozon_browser_total_timeout_seconds: float = 45.0
    ozon_browser_warmup_home: bool = True
    ozon_browser_warmup_seconds: float = 5.0
    ozon_browser_max_retries: int = 1
    ozon_browser_retry_delay_seconds: float = 3.0
    ozon_browser_headless: bool | None = None
    ozon_browser_max_results: int = 30
    ozon_two_stage_enabled: bool = True
    ozon_broad_search_max: int = 36
    ozon_ml_top_k: int = 5
    ozon_enrich_enabled: bool = True
    ozon_enrich_concurrency: int = 1
    ozon_enrich_delay_seconds: float = 5.0
    ozon_enrich_wait_seconds: float = 15.0
    ozon_enrich_timeout_seconds: float = 25.0
    ozon_pipeline_timeout_seconds: float = 180.0
    search_task_poll_interval_seconds: float = 3.0
    ozon_browser_cache_enabled: bool = False
    ozon_browser_cache_ttl_seconds: int = 24 * 60 * 60
    ozon_disk_cache_dir: str = ""


settings = Settings()

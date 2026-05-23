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
    wb_warmup_enabled: bool = True
    wb_session_max_age_seconds: float = 25 * 60
    wb_session_idle_seconds: float = 10 * 60
    wb_search_max_retries: int = 1
    wb_search_retry_delay_seconds: float = 0.5
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
    query_spell_enabled: bool = True
    query_spell_timeout_seconds: float = 4.0
    query_spell_cache_ttl_seconds: int = 86400
    other_search_timeout_seconds: float = 25.0
    other_fetch_concurrency: int = 4
    other_cache_enabled: bool = False
    other_max_results: int = 8


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Tender Hack Price Aggregator"
    debug: bool = False
    redis_url: str = "redis://localhost:6379/0"
    searxng_url: str = "http://localhost:8080"
    cache_ttl_seconds: int = 6 * 60 * 60
    scraper_timeout_seconds: float = 8.0


settings = Settings()

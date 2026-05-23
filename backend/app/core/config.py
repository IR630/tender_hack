from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Tender Hack Price Aggregator"
    debug: bool = False
    redis_url: str = "redis://localhost:6379/0"
    searxng_url: str = "http://localhost:8080"
    cache_ttl_seconds: int = 6 * 60 * 60
    scraper_timeout_seconds: float = 8.0
    ozon_demo_fallback_enabled: bool = True
    ozon_demo_cache_path: str | None = None

    @field_validator("debug", mode="before")
    @classmethod
    def _normalize_debug_value(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip().lower()
        if normalized in {"release", "prod", "production"}:
            return False
        if normalized in {"debug", "dev", "development"}:
            return True
        return value


settings = Settings()

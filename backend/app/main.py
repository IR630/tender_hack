import logging

import structlog
from fastapi import FastAPI

from app.api.routes import regions, search, wb_metrics
from app.core.config import settings

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(message)s" if settings.debug else "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(search.router)
app.include_router(regions.router)
app.include_router(wb_metrics.router)

_startup_logger = logging.getLogger("app.startup")


@app.on_event("startup")
async def log_wb_proxy_config() -> None:
    if settings.wb_proxy.strip():
        _startup_logger.info(
            "WB proxy enabled (max_retries=%s)",
            settings.wb_proxy_max_retries,
        )
    else:
        _startup_logger.warning("WB proxy not configured — direct IP will be used")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/wb")
async def health_wb() -> dict[str, object]:
    proxy_configured = bool(settings.wb_proxy.strip())
    return {
        "proxy_configured": proxy_configured,
        "proxy_max_retries": settings.wb_proxy_max_retries,
        "proxy_parallel_attempts": settings.wb_proxy_parallel_attempts,
        "proxy_race_rounds": settings.wb_proxy_race_rounds,
        "warmup_enabled": settings.wb_warmup_enabled,
        "cache_enabled": settings.wb_cache_enabled,
    }

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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

import logging

import structlog
from fastapi import FastAPI

from app.api.routes import regions, search
from app.core.browser_semaphore import ozon_browser_semaphore
from app.core.config import settings

# Max 1 Chromium/nodriver instance at a time — imported by ozon_browser scraper.
# ozon_browser_semaphore: asyncio.Semaphore(1) in app/core/browser_semaphore.py

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
app.state.ozon_browser_semaphore = ozon_browser_semaphore
app.include_router(search.router)
app.include_router(regions.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

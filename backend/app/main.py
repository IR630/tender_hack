import logging

from fastapi import FastAPI

from app.api.routes import regions, search
from app.core.config import settings

# Without this, app.* loggers (e.g. the scrapers) propagate to a root logger
# that defaults to WARNING with no handler, so their diagnostics never show.
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(search.router)
app.include_router(regions.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

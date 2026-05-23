from fastapi import APIRouter

from app.scrapers.wb.metrics import wb_metrics

router = APIRouter(tags=["metrics"])


@router.get("/metrics/wb")
async def get_wb_metrics() -> dict:
    return wb_metrics.snapshot()

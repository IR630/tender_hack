import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.scrapers.wb.metrics import wb_metrics


@pytest.mark.asyncio
async def test_wb_metrics_endpoint():
    await wb_metrics.reset()
    await wb_metrics.record(success=True, latency_ms=12.5, status_code=200)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics/wb")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_requests"] == 1
    assert payload["success_rate"] == 1.0

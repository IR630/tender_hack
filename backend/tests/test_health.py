import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.tasks.store import search_task_store

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_start_returns_task_id() -> None:
    response = client.post("/search", json={"query": "iphone 15"})
    assert response.status_code == 200
    payload = response.json()
    assert "task_id" in payload
    assert len(payload["task_id"]) == 36


def test_search_task_status_not_found() -> None:
    response = client.get("/search/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_search_task_store_lifecycle() -> None:
    task_id = await search_task_store.create()
    task = await search_task_store.get(task_id)
    assert task is not None
    assert task.status == "pending"

    await search_task_store.set_running(task_id, message="running")
    task = await search_task_store.get(task_id)
    assert task.status == "running"
    assert task.message == "running"


def test_search_mock_returns_groups() -> None:
    response = client.post("/search/mock", json={"query": "iphone 15"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["query"]["original"] == "iphone 15"
    assert payload["query"]["region"] == "moscow"
    assert len(payload["groups"]) == 4


def test_regions_endpoint() -> None:
    response = client.get("/regions")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["id"] == "moscow"
    assert any(region["id"] == "spb" for region in payload)

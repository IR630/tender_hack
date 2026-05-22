from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_returns_grouped_stub() -> None:
    response = client.post("/search", json={"query": "iphone 15"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["query"]["original"] == "iphone 15"
    assert len(payload["groups"]) == 4
    assert {group["source"] for group in payload["groups"]} == {
        "wildberries",
        "ozon",
        "yandex_market",
        "other",
    }

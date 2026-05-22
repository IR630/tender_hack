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
    assert payload["query"]["region"] == "moscow"
    assert payload["query"]["region_name"] == "Москва"
    assert len(payload["groups"]) == 4
    assert {group["source"] for group in payload["groups"]} == {
        "wildberries",
        "ozon",
        "yandex_market",
        "other",
    }


def test_regions_endpoint() -> None:
    response = client.get("/regions")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["id"] == "moscow"
    assert payload[0]["name"] == "Москва"
    assert any(region["id"] == "spb" for region in payload)

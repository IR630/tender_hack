# Backend

FastAPI service for price aggregation.

## Local development

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Module ownership

| Path | Owner |
|---|---|
| `app/scrapers/` | Dev 2 — WB, Ozon, Yandex Market |
| `app/sources/` | Dev 3 — 4th dynamic source |
| `app/query/`, `app/ml/`, `app/api/`, `app/orchestrator/` | Dev 4 — API, ML, orchestration |

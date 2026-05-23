# HTTP API

**Код:** `backend/app/main.py`, `backend/app/api/routes/`

## Bootstrap

```python
app = FastAPI(title=settings.app_name)
app.include_router(search.router)    # /search
app.include_router(regions.router)   # /regions
app.state.ozon_browser_semaphore = ozon_browser_semaphore
```

Logging: structlog JSON + stdlib.

## Эндпоинты

| Method | Path | Описание |
|--------|------|----------|
| GET | `/health` | `{"status":"ok"}` |
| GET | `/regions` | `[{id, name}, ...]` |
| POST | `/search` | Async search → `{task_id}` |
| GET | `/search/{task_id}` | Poll: status, message, groups, result |
| POST | `/search/sync` | Blocking (dev, hidden in OpenAPI) |
| POST | `/search/mock` | Empty skeleton (dev) |

OpenAPI: http://localhost:8000/docs

## Async search

```
POST /search { query, region }
  → search_task_store.create()
  → spawn_search_task(task_id, request)
  → { task_id }

GET /search/{task_id}
  → SearchTaskStatusResponse:
      status: pending | running | completed | failed
      message: progress (RU)
      groups: partial SearchGroup[]
      result: SearchResponse (when completed)
```

404 если task_id не найден или expired (TTL 1 ч).

## Regions

**Код:** `api/routes/regions.py` → `list_regions()` из `core/regions.py`.

## Proxy

| Окружение | Правило |
|-----------|---------|
| Vite dev | `/api/*` → `localhost:8000/*` (strip `/api`) |
| Docker nginx | `/api/` → `127.0.0.1:8000/` |

## Библиотеки

fastapi, uvicorn, pydantic, structlog

## Связанные категории

- [pipeline.md](pipeline.md) — что происходит после POST /search
- [models.md](models.md) — контракты request/response
- [frontend.md](frontend.md) — polling клиента

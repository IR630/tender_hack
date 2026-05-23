# Библиотеки

Справочник зависимостей и их связь с методами обхода.

## Backend (`backend/pyproject.toml`)

### Web

| Package | Роль |
|---------|------|
| fastapi | HTTP API |
| uvicorn | ASGI server |
| pydantic, pydantic-settings | Models, .env |

### HTTP / Scraping

| Package | Маркетплейс / модуль |
|---------|----------------------|
| **curl_cffi** | WB JSON API, YM HTML primary |
| **selectolax** | YM snippets, Ozon tiles/cards |
| **playwright** | YM fallback only |
| **nodriver** | Ozon browser primary |
| **httpx** | Ozon public SearXNG |

### Cache / Search infra

| Package | Роль |
|---------|------|
| redis | WB/YM sync cache, Ozon public async |
| diskcache | Ozon browser disk cache |
| meilisearch-python-sdk | Ozon public URL index |

### ML

| Package | Роль |
|---------|------|
| torch (CPU index) | Backend sentence-transformers |
| sentence-transformers | Ozon ML filter (rubert-tiny2) |
| pandas | Sort ML scores |

### Utils

| Package | Роль |
|---------|------|
| structlog | Ozon browser JSON logs |
| tenacity | Ozon OG fetch retries |

### Dev

pytest, pytest-asyncio, ruff, httpx

## Frontend

react 19, vite 6, typescript, tailwindcss, eslint

## Infra images

redis:7-alpine, searxng/searxng, getmeili/meilisearch

## Матрица: библиотека → обход

```
curl_cffi ──────► Wildberries (JSON)
              └──► Yandex Market (HTML)

playwright ─────► Yandex Market (fallback)

nodriver ───────► Ozon (browser)

httpx ──────────► Ozon public (SearXNG)

meilisearch-sdk ► Ozon public (discovery)

selectolax ─────► Yandex Market + Ozon parsing

sentence-transformers ► Ozon broad → top-5
```

## Stdlib (важное)

asyncio — orchestrator, Ozon browser, task store  
json — cache, Ozon JSON parse  
concurrent.futures — YM card enrichment  
difflib — YM title dedup

## Установка

```bash
cd backend && uv sync
cd frontend && pnpm install
playwright install chromium   # YM fallback
```

## Маркетплейсы

Per-source детали: [../marketplaces/README.md](../marketplaces/README.md)

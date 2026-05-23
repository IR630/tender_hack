# Инфраструктура и деплой

## Регионы

**Код:** `backend/app/core/regions.py`

```python
Region(id, name, yandex_market_id, wb_dest)
```

| id | WB dest | YM yandex_gid |
|----|---------|---------------|
| moscow | -1257786 | 213 |
| spb | -1198059 | 2 |
| kazan | -2133464 | 43 |
| ekaterinburg | -5818943 | 54 |
| novosibirsk | -364763 | 65 |

Ozon browser region не использует. Ozon public — `region.id`.

API: `GET /regions`. Frontend: `RegionSelector` + localStorage.

---

## Browser Semaphore

**Код:** `backend/app/core/browser_semaphore.py`

```python
ozon_browser_semaphore = asyncio.Semaphore(1)
```

Max **1 Chromium** для Ozon nodriver. Очередь при конкуренции пользователей.

Cleanup: `./kill_zombies.sh` — stuck Chromium.

---

## Docker: full stack

**Файл:** `docker/docker-compose.yml`  
**network_mode: host** (VPN/tun workaround)

| Service | Port | Роль |
|---------|------|------|
| api | 8000 | FastAPI + uvicorn |
| frontend | 5173 | nginx + React |
| redis | 6379 | WB/YM cache |
| searxng | 8080 | Meta-search |
| meilisearch | 7700 | Ozon public index |

**API image** (`Dockerfile.api`):

- uv, Python 3.12, Chromium, nodriver
- Xvfb `:99` + `entrypoint-api.sh`

Volumes: `redis_data`, `meili_data`, `ozon_disk_cache`.

---

## Hybrid demo (Ozon)

Ozon с nodriver требует реальный Chromium и графическую сессию. В Docker (Xvfb) WAF блокирует запросы. Решение — **гибрид**: инфраструктура в Docker, API на хосте.

```bash
./start_demo.sh
```

Скрипт:

1. Поднимает Docker: frontend, Redis, SearXNG, MeiliSearch (`docker-compose.hybrid.yml`)
2. Запускает uvicorn на хосте на `:8000` с `DISPLAY=:0` (или через `xvfb-run`, если DISPLAY не задан)

| Сервис | URL |
|--------|-----|
| UI | http://127.0.0.1:5173 |
| API | http://127.0.0.1:8000 |
| Health | http://127.0.0.1:8000/health |

**Остановка:** `Ctrl+C` в терминале со `start_demo.sh`. Зависший Chromium: `./kill_zombies.sh`.

**Env (дефолты в start_demo.sh):** `OZON_USE_BROWSER=true`, `OZON_BROWSER_WARMUP_HOME=true`, `OZON_ENRICH_WAIT_SECONDS=15`, `OZON_PIPELINE_TIMEOUT_SECONDS=180`, `OZON_BROWSER_CACHE_ENABLED=false`.

| Симптом | Решение |
|---------|---------|
| `address already in use :8000` | `fuser -k 8000/tcp` |
| Ozon «сайт блокирует» на первом запросе | `OZON_BROWSER_WARMUP_HOME=true`, retry |
| Описание только у 1 из 5 | `OZON_ENRICH_WAIT_SECONDS=15` |
| UI недоступен | `docker compose -f docker-compose.hybrid.yml up -d` |

---

## CI

`.github/workflows/ci.yml`:

- Backend: uv sync, ruff, pytest (skip `@integration`)
- Frontend: pnpm lint, build

---

## Локальная разработка

```bash
cd backend && uv sync && uv run uvicorn app.main:app --reload
cd frontend && pnpm install && pnpm dev
```

Playwright chromium: `playwright install chromium` (только YM fallback).

---

## Env

Copy `.env.example` → `.env`.

Critical для Ozon demo:

```env
OZON_USE_BROWSER=true
DISPLAY=:0
```

## Связанные документы

- [../docker-run.md](../docker-run.md)
- [../marketplaces/ozon.md](../marketplaces/ozon.md)

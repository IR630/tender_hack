# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Язык общения

Всегда отвечай на **русском языке**, независимо от языка вопроса.

## Commands

### Backend

```bash
cd backend

# Install dependencies
uv sync

# Run API server (hot-reload)
uv run uvicorn app.main:app --reload

# Lint
uv run ruff check .
uv run ruff format .

# Run tests (unit only, no network)
uv run pytest

# Run a single test file
uv run pytest tests/test_wb_scraper.py

# Run integration tests (live network)
uv run pytest -m integration

# Run smoke suite against running server
uv run python scripts/smoke_search.py
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev       # http://127.0.0.1:5173
pnpm build
```

### Infrastructure (Docker)

```bash
# Full stack (Redis, SearXNG, frontend)
cd docker && bash up.sh

# Hybrid: infra in Docker, API on host
docker compose -f docker-compose.hybrid.yml up -d

# Teardown
docker compose down
```

The API runs **on the host** (not in Docker) in the hybrid mode so that Playwright/Ozon can reach a real display.

## Architecture

```
POST /search/task  → spawn_search_task (background)
GET  /search/task/{id} → poll for partial results

POST /search       → run_search (blocking, for direct use)
```

### Request flow

1. **`app/api/routes/search.py`** — HTTP endpoints; the task-based path creates a UUID, fires `spawn_search_task`, and returns immediately for polling.
2. **`app/orchestrator/search.py`** — `run_search_task` / `run_search`; calls `process_query`, resolves region, then fans out to all enabled sources in parallel via `asyncio.gather`.
3. **`app/query/processor.py`** — typo correction (Yandex Speller), then synonym expansion. Cascade: cheap first (Yandex API cached), LLM only as fallback.
4. **Sources** (all return `list[Product]`):
   - `app/scrapers/wb/` — Wildberries JSON API directly; multi-module: `scraper.py` orchestrates, `session.py` manages curl_cffi session, `proxy.py` handles proxy rotation, `rhythm.py` rate-limits, `circuit.py` trips on repeated failures, `assemble.py` normalises raw JSON, `metrics.py` tracks latency.
   - `app/scrapers/yandex_market.py` — curl_cffi + selectolax HTML parsing.
   - `app/scrapers/ozon.py` / `ozon_browser.py` / `two_stage_ozon.py` — Playwright stealth browser; two-stage: broad search then ML re-rank (`ozon_ml_filter.py`).
   - `app/sources/other/search.py` — 4th dynamic source: SearXNG → top-3 domains → Schema.org JSON-LD → regex → (vision fallback).
5. **`app/orchestrator/search.py`** groups results into `SearchGroup` per source, builds `SearchSummary` (min/median/max price), returns `SearchResponse`.

### Shared data model

`app/core/models.py` defines `Product`, `SearchGroup`, `SearchRequest`, `SearchResponse`, `SearchSummary`, `SearchQuery`. Prices are stored in **kopecks** (integers) to avoid float rounding.

### Configuration

All tunables live in `app/core/config.py` (`Settings` via pydantic-settings). Values are read from `backend/.env` or `.env` at repo root. Key env vars:

| Variable | Purpose |
|---|---|
| `SEARCH_ENABLED_SOURCES` | Comma-separated subset: `wildberries,yandex_market,other,ozon` |
| `WB_PROXY` | Proxy URL for WB requests |
| `REDIS_URL` | Cache backend |
| `SEARXNG_URL` | Self-hosted SearXNG for 4th source |
| `OZON_USE_BROWSER` | Toggle Playwright mode |
| `QUERY_SPELL_ENABLED` | Enable/disable Yandex speller |

### Cache

`app/core/cache.py` wraps `diskcache`. Cache keys follow `{source}:search:{region}:{query}`. TTL defaults to 6 hours. The WB scraper additionally uses `wb_metrics` for per-session performance tracking.

### Anti-bot layers

- **WB**: direct JSON API (`search.wb.ru`, `card.wb.ru`) — no browser needed, but rate-limited by `rhythm.py` (min 1.5 s between requests) and circuit-broken after failures.
- **Yandex Market**: `curl_cffi` with `chrome120` TLS impersonation.
- **Ozon**: Playwright + `playwright-stealth`; persistent browser context reused across requests; `browser_semaphore.py` limits concurrent browser sessions.

### Hackathon constraints

Per `docs/ARCHITECTURE_CONSTRAINTS.md`:
- No external search APIs (Google, Bing, Yandex Search API).
- No external LLM APIs (OpenAI, OpenRouter, etc.). Use Ollama locally.
- No Cloudflare Workers or third-party SaaS in runtime. Use own VPS for proxy if needed.
- 4th source must be **dynamic** (different domains per query) — SearXNG self-hosted satisfies this.

## Key test markers

- Default `pytest` run skips `integration` tests (live network). Pass `-m integration` to include them.
- `asyncio_mode = "auto"` — all async test functions work without explicit decorators.

## Frontend

React + Vite + Tailwind + shadcn/ui. Entry: `frontend/src/App.tsx`. Types for API responses are in `frontend/src/types/search.ts` (keep in sync with `app/core/models.py`).

# Ozon Public Scraper (HONEST approach)

Sitemap + SearXNG + Open Graph — без внутренних API Ozon.

## Quick start

```bash
# Infrastructure
cd docker && docker compose up -d redis searxng meilisearch

# Backend
cd backend && uv sync

# Rebuild Meilisearch index (offline, cron)
uv run python -m ozon_public_scraper.jobs.rebuild_index

# Search
uv run python -c "
import asyncio
from ozon_public_scraper import OzonPublicScraper
async def main():
    r = await OzonPublicScraper(region='spb').search('кроссовки nike', limit=5)
    for p in r: print(p.title, p.price_rub, p.incomplete)
asyncio.run(main())
"
```

## Environment

| Variable | Default | Description |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | OG + SearXNG cache |
| `SEARXNG_URL` | `http://localhost:8080` | Self-hosted metasearch |
| `MEILI_URL` | `http://localhost:7700` | Meilisearch |
| `MEILI_MASTER_KEY` | — | Meilisearch API key |
| `OZON_PUBLIC_LOG_DIR` | `./logs` | JSONL logs |
| `OZON_MAX_CONCURRENT` | `2` | Max parallel Ozon fetches |
| `OZON_SEARXNG_CACHE_TTL` | `1800` | SearXNG cache (30 min) |
| `OZON_OG_CACHE_TTL` | `3600` | OG cache (1 h) |
| `OZON_OG_INCOMPLETE_CACHE_TTL` | `300` | Short TTL when price missing |

## Pipelines

1. **A — Sitemap → Meilisearch** (offline): `jobs/rebuild_index.py`
2. **B — SearXNG** (online): `site:ozon.ru <query>`
3. **C — OG fetcher** (online): parse `og:*` / `product:*` / JSON-LD

## Logs

`./logs/ozon_public_{date}.jsonl`

```bash
jq 'select(.event=="query_completed")' logs/ozon_public_*.jsonl
jq 'select(.event=="ozon_blocked_og_fetch")' logs/ozon_public_*.jsonl | wc -l
```

## Tests

```bash
uv run pytest ozon_public_scraper/tests/ -q
```

## Forbidden (by design)

- `composer-api.bx`, `entrypoint-api.bx`, any `/api/*` Ozon endpoints
- Mobile app headers (`x-o3-*`, `ozonapp_android`)
- Headless browsers (unless `OZON_ENABLE_BROWSER_FALLBACK=true`)

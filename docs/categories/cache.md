# Кэширование

В проекте **три независимых слоя** кэша.

## 1. Redis sync — WB и YM

**Код:** `backend/app/core/cache.py`

| | |
|--|--|
| Клиент | sync `redis`, graceful degradation |
| TTL | `CACHE_TTL_SECONDS` = 6 ч |
| API | `cache_get(key)`, `cache_set(key, value, ttl)` |

### Keys

| Scraper | Pattern |
|---------|---------|
| Wildberries | `wb:search:{region}:{query.lower()}` |
| Yandex Market | `ym:search:{region}:{query.lower()}` |

Value: JSON array of Product dicts.

Флаги: `WB_CACHE_ENABLED`, `YM_CACHE_ENABLED`.

Redis down → scrapers работают без кэша (warning в log).

---

## 2. Diskcache — Ozon browser

**Код:** `backend/cache_manager.py`

| | |
|--|--|
| Backend | **diskcache** (SQLite filesystem) |
| Dir | `OZON_DISK_CACHE_DIR` или `backend/data/ozon_disk_cache` |
| Key | `query.strip().lower()` |
| TTL | 24 ч (default) |
| Флаг | `OZON_BROWSER_CACHE_ENABLED` (default false) |

Используется в `ozon_browser.search_products` и `two_stage_ozon` — при hit **браузер не запускается**.

Docker volume: `ozon_disk_cache`.

---

## 3. Redis async — Ozon public

**Код:** `backend/ozon_public_scraper/storage/cache.py`

| Key | Content |
|-----|---------|
| `searxng:{query}` | ProductUrl[] |
| `og:{numeric_id}` | ProductResult JSON |
| `ozon_blocked:{numeric_id}` | blocked flag |

Отдельный `redis.asyncio` client. Только path `OZON_USE_BROWSER=false`.

---

## Сравнение

| Layer | Sync/Async | Scope | Default |
|-------|------------|-------|---------|
| app/core/cache.py | sync | WB, YM | on |
| cache_manager.py | sync | Ozon browser | off |
| ozon_public cache | async | SearXNG, OG | on if public path |

## Конфиг

```env
REDIS_URL=redis://localhost:6379/0
CACHE_TTL_SECONDS=21600
WB_CACHE_ENABLED=true
YM_CACHE_ENABLED=true
OZON_BROWSER_CACHE_ENABLED=false
OZON_BROWSER_CACHE_TTL_SECONDS=86400
OZON_DISK_CACHE_DIR=...
```

## Библиотеки

redis, diskcache, json

## Маркетплейсы

Детали per-source: [../marketplaces/wildberries.md](../marketplaces/wildberries.md), [../marketplaces/yandex-market.md](../marketplaces/yandex-market.md), [../marketplaces/ozon.md](../marketplaces/ozon.md)

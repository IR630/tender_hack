# Ozon

**Код:**

| Модуль | Путь |
|--------|------|
| Facade | `backend/app/scrapers/ozon.py` |
| Browser | `backend/app/scrapers/ozon_browser.py` |
| Two-stage | `backend/app/scrapers/two_stage_ozon.py` |
| Парсинг | `backend/app/scrapers/ozon_seo_common.py` |
| ML filter | `backend/app/scrapers/ozon_ml_filter.py` |
| Disk cache | `backend/cache_manager.py` |
| Public path | `backend/ozon_public_scraper/` |

**source:** `ozon`

## Идея

Ozon блокирует HTTP (curl, proxy, mobile API) через FAB/WAF. **Рабочий путь — Chromium через nodriver** на хосте с `DISPLAY`. Пайплайн: broad search (36) → ML top-5 → enrich карточек — **в одной сессии браузера**.

Fallback без браузера: MeiliSearch + SearXNG + OG fetch.

## Выбор режима

```python
# ozon.py
if settings.ozon_use_browser:
    return await _search_browser(request)   # default
return await _search_public(request)
```

| Режим | Env | Обход |
|-------|-----|-------|
| Browser two-stage | `OZON_USE_BROWSER=true`, `OZON_TWO_STAGE_ENABLED=true` | nodriver → ML → enrich |
| Browser single-stage | `OZON_TWO_STAGE_ENABLED=false` | nodriver → extract 30 |
| Public | `OZON_USE_BROWSER=false` | Meili + SearXNG + httpx OG |

---

## Режим A: Browser + Two-Stage (production)

### Общий поток

```
query
  │
  ▼
run_browser_pipeline()          ← одна сессия Chromium, semaphore max 1
  │
  ├─ warmup https://www.ozon.ru/  (cookies, WAF)
  ├─ [1] search URL → extract_broad_search_products (до 36)
  ├─ [2] filter_top_k_by_similarity (rubert-tiny2, top-5)
  └─ [3] для каждого top-k (пауза 5s):
         navigate product URL → wait SPA → extract_product_enrichment
  │
  ▼
dict[] → OzonScraper → Product[] → API → UI
```

### Browser layer (`ozon_browser.py`)

**nodriver** — CDP automation без webdriver flag.

```
async with ozon_browser_semaphore:     # max 1 Chromium
    browser = nodriver.start(headless=..., lang=ru-RU)
    warmup ozon.ru
    handler(browser)                   # timeout OZON_PIPELINE_TIMEOUT_SECONDS
    browser.stop()
```

**Warmup:** без него первый search часто даёт ложный `blocked_by_waf`.

**Polling** (`_poll_until_ready`, каждые 2 с):

| Режим | Ready when |
|-------|------------|
| search | `/product/` in HTML + `₽` |
| product detail | `og:description` ≥10 chars OR ≥20 `data-widget` |
| warmup | not challenge page |

На карточке: `scroll_down(1200)` + sleep 2s.

**WAF detection:**

```python
CHALLENGE_TITLES = ("Antibot Captcha", "Antibot Challenge Page", "Доступ ограничен")
len(html) < 15000 and "antibot" in html
```

→ `SearchGroup.status = "blocked_by_waf"`, UI показывает плашку.

### Two-stage (`two_stage_ozon.py`)

**Этап 1 — Broad search**

- URL: `https://www.ozon.ru/search/?text={query}`
- `extract_broad_search_products(html, max=36)`
- Только main grid, без рекомендаций/рекламы

**Этап 2 — ML filter** (`ozon_ml_filter.py`)

- Модель: `cointegrated/rubert-tiny2` (sentence-transformers)
- Cosine similarity query ↔ title
- Top `OZON_ML_TOP_K` (5)
- Fallback: первые 5 без ML при ошибке

**Этап 3 — Enrich**

- `OZON_ENRICH_DELAY_SECONDS=5` между карточками
- `extract_product_enrichment` → description + characteristics
- `description` = prose + «Характеристики: • ключ: значение»
- Сбой одной карточки **не abort'ит** пайплайн — остаётся preview

### Парсинг HTML/JSON (`ozon_seo_common.py`)

**Broad search — приоритет extractors:**

1. `widgetStates` из `window.__NUXT__.state`
2. `__NEXT_DATA__` script JSON
3. HTML cards `div.tile-root` (fallback)

Фильтры: badge titles, реклама, placeholder images, dedup URL, price > 0.

**Enrichment — источники:**

1. `__NEXT_DATA__` / `__NUXT__.state` JSON
2. JSON-LD `@type: Product`
3. HTML `dl`, `[data-widget="webCharacteristics"]`
4. Meta `og:description`

**Библиотека:** selectolax + json/re.

### Disk cache (`cache_manager.py`)

При `OZON_BROWSER_CACHE_ENABLED=true`:

- **diskcache** в `backend/data/ozon_disk_cache`
- Key: `query.strip().lower()`
- TTL: 24 ч (default)
- Hit → браузер не запускается

### Типичное время

| Фаза | Время |
|------|-------|
| Warmup + search | 10–40 с |
| ML (cold start модели) | 2–10 с первый раз |
| 5 × enrich | ~100 с |
| **Итого** | 35–180 с |

---

## Режим B: Browser single-stage

`OZON_TWO_STAGE_ENABLED=false`:

```
fetch search HTML → extract_products(max=30) → optional disk cache
```

Без ML и enrich.

---

## Режим C: Public scraper (`ozon_public_scraper/`)

```
query
  ├─ parallel MeiliSearch.search
  └─ parallel SearXNG site:ozon.ru {query}
  │
  ▼
merge URLs by numeric_id
  │
  ▼
parallel fetch_product_og (httpx + tenacity retries)
  │
  ▼
ProductResult[] → OzonScraper._search_public
```

| Компонент | Роль |
|-----------|------|
| `storage/meili.py` | Index search по slug/url |
| `pipelines/searxng.py` | httpx → SearXNG JSON |
| `pipelines/og_fetcher.py` | Fetch page, extract OG |
| `parsers/og_extractor.py` | og:title, price, image |
| `storage/cache.py` | async Redis: searxng, og, blocked |

403 на OG → retry → mark blocked. 404 → delete from Meili.

**Не demo path** — WAF часто блокирует HTTP fetch карточек.

---

## Маппинг в Product (`ozon.py`)

| dict / ProductResult | Product |
|----------------------|---------|
| title | title |
| price / price_rub | price (копейки) |
| url / product_url | product_url |
| image / image_url | image_url |
| characteristics | characteristics |
| description | description |
| incomplete | `characteristics["price_unavailable"]="true"` |

## Конфиг (.env)

```env
OZON_USE_BROWSER=true
OZON_TWO_STAGE_ENABLED=true
OZON_BROAD_SEARCH_MAX=36
OZON_ML_TOP_K=5
OZON_ENRICH_ENABLED=true
OZON_ENRICH_DELAY_SECONDS=5
OZON_ENRICH_WAIT_SECONDS=15
OZON_PIPELINE_TIMEOUT_SECONDS=180
OZON_BROWSER_WARMUP_HOME=true
OZON_BROWSER_CACHE_ENABLED=false
OZON_DISK_CACHE_DIR=...
```

## Библиотеки

| Пакет | Где |
|-------|-----|
| nodriver | Browser automation |
| selectolax | HTML parse |
| sentence-transformers + torch | ML filter |
| pandas | Sort similarities |
| structlog | JSON logs |
| diskcache | Browser results |
| httpx, meilisearch-sdk, tenacity | Public path |

## Место в общем пайплайне

Ozon запускается **последним** (после parallel WB/YM/Other) — держит глобальный semaphore Chromium.

## Hybrid demo

Ozon **не работает в Docker Xvfb** → API на хосте с `DISPLAY=:0`. См. [../categories/infrastructure.md](../categories/infrastructure.md).

## Тесты

- `tests/test_ozon_seo_common.py`
- `tests/test_two_stage_ozon.py`
- `tests/test_cache_manager.py`
- `ozon_public_scraper/tests/`

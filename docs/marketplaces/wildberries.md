# Wildberries

**Код:** `backend/app/scrapers/wb.py`  
**Класс:** `WildberriesScraper` (`scraper`)  
**source:** `wildberries`

## Идея

Самый лёгкий источник: **один HTTP JSON-запрос** на cache miss. Без браузера, без enrichment карточек — чтобы не сжечь egress IP.

## Пайплайн обхода

```
SearchRequest (query, region)
    │
    ▼
resolve_region → region.wb_dest
    │
    ▼
Redis wb:search:{region}:{query} ?
    ├─ hit  → Product[]
    └─ miss
         │
         ▼
    circuit breaker open? → error, []
         │
         ▼
    _throttle_wb()  (~1.5s + jitter)
         │
         ▼
    GET search.wb.ru/exactmatch/ru/common/v4/search
         │ curl_cffi, impersonate chrome131 (настройка wb_impersonate)
         ▼
    JSON products[] → _assemble_products → Redis set → return (max 30)
```

## HTTP-обход

| Параметр | Значение |
|----------|----------|
| URL | `https://search.wb.ru/exactmatch/ru/common/v4/search` |
| Метод | GET |
| Библиотека | **curl_cffi** (`Session(impersonate=settings.wb_impersonate)`, дефолт `chrome131`) |
| Query params | `query`, `dest`, `resultset=catalog`, `curr=rub`, `lang=ru`, `appType=1`, `page=1` |
| Timeout | `scraper_timeout_seconds` (8 с) |

### Заголовки

- `Origin`, `Referer`: `wildberries.ru`
- `x-userid: 0`
- `x-queryid`: `qid{timestamp_ms}` — уникальный на каждую попытку
- `User-Agent` / `sec-ch-ua` **не задаём вручную** — их выставляет curl_cffi под
  выбранный профиль `impersonate`, чтобы UA-строка не расходилась с TLS-отпечатком

## Парсинг JSON → Product

| Product | JSON |
|---------|------|
| title | `name` |
| price | `sizes[0].price.product` / `salePriceU` (**копейки**) |
| product_url | `https://www.wildberries.ru/catalog/{nm}/detail.aspx` |
| image_url | basket CDN по volume hint |
| characteristics | `brand`, `supplier` |
| rating | `reviewRating`, `nmReviewRating` |
| reviews_count | `nmFeedbacks`, `feedbacks` |

Фильтр: пропускаем товары без `id`, `name` или с `price <= 0`.

### Basket CDN

Таблица `_HOST_HINT_RANGES`: `nm // 100000` → host `basket-NN.wbbasket.ru`:

```
https://basket-{host}/vol{vol}/part{part}/{nm}/images/big/1.webp
```

## Защита от блокировок

| Механизм | Env | Поведение |
|----------|-----|-----------|
| Rate limit | `WB_MIN_REQUEST_INTERVAL_SECONDS=1.5` | asyncio Lock + sleep + 20% jitter |
| Retry + backoff | `WB_RETRY_MAX_ATTEMPTS=3`, `WB_RETRY_BACKOFF_BASE_SECONDS=0.5`, `WB_RETRY_MAX_BACKOFF_SECONDS=5` | при 429/498 — повтор с экспоненциальным backoff + jitter; учитывается заголовок `Retry-After` (под потолком); новый `x-queryid` |
| Session reset | — | новый Session при каждой блокировке |
| Circuit breaker | `WB_CIRCUIT_BREAKER_SECONDS=600` | когда попытки исчерпаны блокировкой — 10 мин пауза без обращений к WB |

### Коды ошибок

- **429** — rate-limit / антибот
- **498** — домашний антибот WB
- **x-pow** — PoW challenge (может быть при HTTP 200 и 0 товаров)

Ошибки попадают в `SearchGroup.error` через `scraper.last_error`.

## Регион

`Region.wb_dest` из `core/regions.py`:

| region | wb_dest |
|--------|---------|
| moscow | -1257786 |
| spb | -1198059 |
| kazan | -2133464 |
| ekaterinburg | -5818943 |
| novosibirsk | -364763 |

## Кэш

- **Ключ:** `wb:search:{region}:{query.lower()}`
- **Backend:** Redis (`app/core/cache.py`)
- **TTL:** `CACHE_TTL_SECONDS` (6 ч)
- **Флаг:** `WB_CACHE_ENABLED=true`

## Библиотеки

| Пакет | Роль |
|-------|------|
| curl_cffi | TLS fingerprint Chrome (профиль `wb_impersonate`, дефолт `chrome131`) |
| asyncio | throttle, `to_thread` для sync HTTP |
| redis | через `cache.py` |

## Что отключено намеренно

- Playwright / nodriver
- Enrichment карточек
- Пагинация (только page=1)

## Конфиг (.env)

```env
WB_IMPERSONATE=chrome131
WB_MIN_REQUEST_INTERVAL_SECONDS=1.5
WB_RETRY_MAX_ATTEMPTS=3
WB_RETRY_BACKOFF_BASE_SECONDS=0.5
WB_RETRY_MAX_BACKOFF_SECONDS=5
WB_CIRCUIT_BREAKER_SECONDS=600
WB_CACHE_ENABLED=true
SCRAPER_TIMEOUT_SECONDS=8
```

## Место в общем пайплайне

Запускается **parallel** с YM и Other в оркестраторе. Типичное время: **1–3 с**.

## Тесты

`backend/tests/test_wb_scraper.py`

# Яндекс Маркет

**Код:** `backend/app/scrapers/yandex_market.py`  
**Класс:** `YandexMarketScraper` (`scraper`)  
**source:** `yandex_market`

## Идея

HTML-выдача через **curl_cffi** (primary), при пустой выдаче или ошибке — **Playwright** fallback. После snippets — parallel enrichment карточек (описание + характеристики).

## Пайплайн обхода

```
SearchRequest
    │
    ▼
Redis ym:search:{region}:{query} ? → hit → return
    │
    miss
    ▼
[Primary] _fetch_products_sync (curl_cffi)
    │
    ├─ OK, products > 0 → cache → return
    └─ empty / exception
         ▼
[Fallback] _fetch_with_playwright
    │
    ├─ OK → cache → return
    └─ error → SearchGroup.error
```

### Primary: curl_cffi

```
Session(impersonate="chrome120")
    │
    ├─ cookie yandex_gid = region.yandex_market_id
    ├─ warmup GET market.yandex.ru/
    ├─ paginated /search?text=...&page=N  (до 3 страниц, delay 0.8s)
    ├─ _parse_search_html (selectolax)
    ├─ filter garbage / duplicates
    └─ _enrich_products (4 parallel HTTP GET на карточки)
```

### Fallback: Playwright

Условие: curl вернул 0 товаров или exception.

```
chromium.launch(headless=True)
    ├─ cookie yandex_gid
    ├─ anti-webdriver init script
    ├─ goto search pages (networkidle)
    └─ тот же parse + enrich pipeline
```

## Парсинг выдачи (selectolax)

Селекторы внутри `article`:

| Поле | CSS |
|------|-----|
| title | `[data-auto="snippet-title"]` |
| price | `[data-auto="snippet-price-current"]` |
| link | `a[href*="/product/"], a[href*="/card/"]` |
| image | `img[src]` |
| reviews | `[data-auto="reviews"]` |
| delivery | `[data-auto="delivery-wrapper"]` |

Цена: regex цифр × 100 → **копейки**.

### Эвристики фильтрации

**Garbage keywords:** чехол, стекло, кабель, зарядка, наушники… — отсекаются, если запрос не про аксессуары.

**Query tokens:** title должен содержать токен запроса (stop-words исключены).

**Duplicates:** URL key + `SequenceMatcher` ≥ 0.93 на normalized title.

### Enrichment карточек

`ThreadPoolExecutor(max_workers=4)` — GET product URL:

- `[data-auto="product-description"]` → prose
- `[data-auto="product-spec"]` → specs
- `description` = prose + «Характеристики: • …» + рейтинг/доставка
- `confidence: 0.95` если есть specs или prose

## Детекция блокировки

```python
"smartcaptcha" in html
"подтвердите, что запросы отправляли вы" in html
403 + len(html) < 10000
```

## Регион

Cookie `yandex_gid` = `Region.yandex_market_id`:

| region | yandex_market_id |
|--------|------------------|
| moscow | 213 |
| spb | 2 |
| kazan | 43 |
| ekaterinburg | 54 |
| novosibirsk | 65 |

## Кэш

- **Ключ:** `ym:search:{region}:{query.lower()}`
- **Redis** sync, TTL 6 ч
- **Флаг:** `YM_CACHE_ENABLED=true`

## Библиотеки

| Пакет | Роль |
|-------|------|
| curl_cffi | Primary HTTP, chrome120 |
| selectolax | HTML parse |
| playwright | Fallback browser (async) |
| difflib.SequenceMatcher | Dedup titles |
| ThreadPoolExecutor | Parallel card fetch |

## Конфиг

```env
YM_SEARCH_MAX_PAGES=3
YM_CACHE_ENABLED=true
CACHE_TTL_SECONDS=21600
```

## Место в общем пайплайне

**Parallel** с WB и Other. Типичное время: **5–20 с**.

## Ограничения

- Нет nodriver
- Garbage filter — keyword stub, не ML
- Region только через cookie

## Тесты

`backend/tests/test_yandex_market.py`

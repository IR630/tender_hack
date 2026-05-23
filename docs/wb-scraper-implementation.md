# Wildberries scraper — идея и реализация

Как устроен парсер WB в `backend/app/scrapers/wb.py`: архитектурная идея,
компромиссы и что делать, если перестанет работать.

## Идея в одном абзаце

Wildberries отдаёт каталог через **внутренний JSON API поиска** (`search.wb.ru`),
который питает веб и мобильные клиенты. Браузер не нужен: один GET-запрос с
браузерными заголовками и **подменой TLS-отпечатка** (`curl_cffi`) возвращает до
100 товаров с ценой, названием, рейтингом. Картинки собираются **математически**
из `nm` (артикула) и таблицы basket-хостов — без дополнительных запросов к CDN.

---

## Почему не Playwright

| Подход | Плюсы | Минусы |
|--------|-------|--------|
| **HTTP + curl_cffi** (текущий) | ~1 запрос, <1 с, мало трафика | WAF режет небраузерный TLS |
| Playwright | Проходит домашний антибот | Chromium в Docker, 5–15 с, много трафика |

Для хакатона выбран **low-footprint mode**: минимум запросов, максимум предсказуемости.
Playwright оставлен как запасной путь (см. `docs/wb-scraper-findings.md`), но в коде отключён.

---

## Поток данных

```
SearchRequest (query, region)
        │
        ▼
   Redis cache hit? ──yes──► list[Product]
        │ no
        ▼
   Circuit breaker open? ──yes──► error + []
        │ no
        ▼
   Rate limit (1.5s + jitter)
        │
        ▼
   GET search.wb.ru/.../v4/search
   params: query, dest, page, appType, ...
        │
        ▼
   JSON products[] ──► map fields ──► list[Product]
        │
        ▼
   Redis cache set (TTL 6h)
```

### Эндпоинт

```
GET https://search.wb.ru/exactmatch/ru/common/v4/search
```

Ключевые параметры:

- `query` — текст пользователя
- `dest` — региональная зона доставки (из `app/core/regions.py`, для СПб: `-1198059`)
- `resultset=catalog`, `curr=rub`, `lang=ru`, `appType=1`, `page=1`

### Заголовки

Имитация браузера на wildberries.ru:

- `Origin`, `Referer` → `https://www.wildberries.ru/`
- `Accept-Language: ru-RU`
- `x-userid: 0`, `x-queryid: qid{timestamp}` — как у фронта

### TLS

```python
curl_requests.Session(impersonate="chrome120")
```

Обычный `httpx`/`requests` получает **429** из-за JA3/JA4. `curl_cffi` с impersonate
проходит WAF и получает **200** + JSON (подробнее — `docs/wb-scraper-findings.md`).

---

## Маппинг полей

| Поле Product | Источник в JSON |
|--------------|-----------------|
| `title` | `products[i].name` |
| `price` | `sizes[0].price.product` (копейки) или `salePriceU` |
| `product_url` | `https://www.wildberries.ru/catalog/{id}/detail.aspx` |
| `image_url` | формула basket CDN (см. ниже) |
| `rating` | `reviewRating` / `nmReviewRating` |
| `reviews_count` | `nmFeedbacks` / `feedbacks` |
| `characteristics` | `brand`, `supplier` из search-ответа |

Товары без `id`, `name` или с `price <= 0` отбрасываются.

---

## Картинки без CDN-проб

WB хранит фото на `basket-{N}.wbbasket.ru`. Номер basket зависит от `vol = nm // 100000`.

Вместо HEAD-запросов к CDN (дорого по IP) используется **захардкоженная таблица**
`_HOST_HINT_RANGES`: пары `(max_vol, host_number)`. По `nm` вычисляется URL:

```
https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{nm}/images/big/1.webp
```

Обогащение через `card.wb.ru/card.json` **отключено** — экономия трафика и запросов.
Характеристики минимальные (бренд + продавец из search).

---

## Защита инфраструктуры

### Rate limit

```python
WB_MIN_REQUEST_INTERVAL_SECONDS=1.5  # + random jitter 0–20%
```

Глобальный lock + `asyncio.sleep` между запросами.

### Circuit breaker

После двух **429/498** подряд — пауза `WB_CIRCUIT_BREAKER_SECONDS` (600 с).
Сессия `curl_cffi` сбрасывается, в UI — понятная ошибка.

### Redis cache

Ключ: `wb:search:{region}:{query}`. При cache hit — **ноль HTTP-запросов**.
TTL: `CACHE_TTL_SECONDS` (6 ч).

---

## PoW (Proof-of-Work)

WB иногда шлёт заголовок `X-Pow: status=invalid;challenge=...`. Это scrypt-hashcash
в WASM (см. findings). **Сейчас решать не нужно**: при `curl_cffi` + chrome API
отдаёт 100 товаров даже с `status=invalid`. Код только **логирует** наличие PoW:

```python
_log_search_diagnosis(pow_header, products, query)
```

Если WB снова начнёт отдавать `[]` при invalid PoW — фоллбэки: WASM через wasmtime
или Playwright warm-up.

---

## Async-обёртка

Публичный API скрапера — `async def search()`. Синхронный `curl_cffi` вызывается
через `asyncio.to_thread()`, Redis — тоже. Так скрапер встраивается в FastAPI
orchestrator без блокировки event loop.

---

## Интеграция с оркестратором

`app/orchestrator/search.py` параллельно дергает WB, Ozon, YM. WB-скрапер:

- наследует `BaseScraper`
- выставляет `last_error` при блокировке
- возвращает `[]` при ошибке (деградация, не падение всего поиска)

---

## Диагностика

Логи (уровень INFO/WARNING/ERROR):

- `WB cache hit` — ответ из Redis
- `WB search blocked: HTTP 429` — WAF / IP
- `WB search OK: N products (PoW header present, results served anyway)`
- `WB scraper funnel: X raw -> Y usable -> Z returned (1 HTTP request)`

По воронке видно: API ответил, но фильтр отсеял товары, или API вернул пустоту.

---

## Ограничения текущей версии

1. **Один HTTP-запрос** — только первая страница (~30 товаров после slice).
2. **Нет card.json** — характеристики только brand/supplier.
3. **Нужен российский IP** — VPN/датацентр → 429/498.
4. **PoW не реализован** — работает пока WB не блокирует по invalid challenge.

---

## Чеклист для Ozon (аналогия)

Подход WB можно перенести на Ozon с поправками:

| WB | Ozon (гипотеза) |
|----|-----------------|
| `search.wb.ru/v4/search` | `api.ozon.ru/composer-api.bx/page/json/v2` |
| `dest` для региона | cookie/header location_id СПб |
| `products[]` flat JSON | `widgetStates` → parse BDUI |
| basket CDN formula | `tileImage.items[0].image.link` |
| curl_cffi chrome120 | curl_cffi chrome131 + mobile headers |
| 1 запрос | 1 POST с `url=/search/?text=...` |

Главное отличие Ozon — **Composer BDUI** (JSON-строки в `widgetStates`) и более
агрессивный Antibot (403 даже через mobile proxy). WB проще: один flat endpoint.

---

## Связанные файлы

- `backend/app/scrapers/wb.py` — реализация
- `backend/tests/test_wb_scraper.py` — юнит-тесты (HTTP замокан)
- `docs/wb-scraper-findings.md` — живые эксперименты, гейты антибота, TODO PoW
- `app/core/regions.py` — `wb_dest` по регионам

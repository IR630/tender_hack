# 4-й источник — план реализации

Документ фиксирует архитектурные решения, принятые в ходе design-сессии.

---

## Принятые решения

| Решение | Выбор |
|---------|-------|
| Discovery | SearXNG (self-hosted) + mini-index в Meilisearch |
| Fallback на блокировку поисковиков | Mini-index по категориям (pre-crawl + incremental) |
| Extraction | Adapter-stack гибрид: JSON-LD generic + per-domain CSS |
| Усилия по категориям | Неравномерно: 3 адаптера оргтехника, 2 шины, 1 одежда |
| Фильтр мусора | 3 уровня: domain blacklist → ML cosine → sanity |
| Mini-index | Pre-crawl ~1500 URL + incremental от live-запросов |
| Код | Клон `ozon_public_scraper/` → `other_public_scraper/` |
| HTTP-транспорт | `curl_cffi` для page fetch, `httpx` для SearXNG/Meili/sitemap |
| LLM в hot path | **Dual-mode**: выключена на CPU (dev), включена на GPU-VPS (demo) через `OTHER_LLM_ENABLED` |
| Browser fallback | Отдельный nodriver-инстанс с собственным семафором, **не** Ozon-овским |

---

## Проблема, которая мотивирует архитектуру

Произвольный HTML не всегда парсится без LLM. Конкретные провалы adapter-stack:

- **SPA с lazy-loaded ценой.** HTML возвращает 200 OK, но `<div id="price"></div>` пустой — цена рендерится после AJAX. curl_cffi видит пустоту, Schema.org/OG отсутствуют.
- **Cloudflare/DataDome HTML-stub.** 200 OK, ~3KB фейкового контента с «Loading…». Парсер вытащит мусор.
- **WASM/canvas-цены.** Редко, но встречается у магазинов с активной защитой.
- **Региональные магазины без Schema.org.** Старая вёрстка, нет JSON-LD/OG, цена в `<span class="prc-val">` без подсказок. Regex `\d+₽` ловит и цену доставки, и зачёркнутую.

Решение — **каскадная деградация**: чем хуже структура страницы, тем тяжелее инструмент включаем. На CPU доступны только Tier 1 и Tier 2. На GPU-VPS подключаются Tier 1.5 (LLM-валидатор) и Tier 2.5 (LLM-экстрактор) — закрывают оставшиеся ~10% сайтов.

---

## Dual-mode: CPU dev vs GPU demo

| Слой | CPU dev | GPU demo (VPS) |
|------|---------|----------------|
| SearXNG discovery | ✅ | ✅ |
| Mini-index Meili | ✅ | ✅ |
| extruct + adapters | ✅ | ✅ |
| rubert-tiny2 validator | ✅ | ✅ |
| **LLM-валидатор серых случаев** | ❌ (no-op) | ✅ Qwen2.5-3B |
| Browser fallback (SPA) | ✅ (но медленнее) | ✅ |
| **LLM-экстрактор для нестандартных** | ❌ | ✅ Qwen2.5-7B |
| Background LLM mini-index enrichment | ❌ | ✅ |

Переключатель — **один env flag** `OTHER_LLM_ENABLED`. Код один, поведение разное.

```python
# backend/other_public_scraper/ml/llm.py
class LLMClient:
    def __init__(self):
        if not settings.other_llm_enabled:
            self.endpoint = None  # no-op для CPU dev
        else:
            self.endpoint = settings.llm_endpoint_url  # vLLM/Ollama на VPS

    async def validate(self, text: str, query: str) -> bool:
        if not self.endpoint:
            return True  # доверяем regex+rubert-tiny2, не блокируем pipeline
        return await self._call_llm(text, query)
```

### Рекомендации по моделям

| Задача | Модель | VRAM | Latency на 4090 |
|--------|--------|------|-----------------|
| Бинарный валидатор | Qwen2.5-3B-Instruct (4-bit) | ~2 GB | ~2 сек |
| JSON-экстрактор | Qwen2.5-7B-Instruct (4-bit) | ~5 GB | ~6 сек |
| Альтернатива | GigaChat-Lite-Instruct | ~6 GB | ~8 сек (лучше русский) |

Раннер: **vLLM** (быстрый, OpenAI-совместимый API) или **Ollama** (проще поднять). Квантизация 4-bit через AWQ/GGUF.

---

## Структура модуля

```
backend/other_public_scraper/
├── __init__.py
├── config.py                   # DOMAIN_ADAPTERS, CATEGORY_KEYWORDS, BLACKLIST
├── models.py                   # ProductCandidate (url, domain, category, snippet_title)
├── scraper.py                  # entry: search_other(query, region) -> list[Product]
├── pipelines/
│   ├── searxng.py             # клон ozon; без site:ozon.ru; + -site:wb -ozon -yandex
│   ├── sitemap.py             # обход sitemap нескольких доменов по списку
│   ├── meili_index.py         # чтение/запись индекса other_products
│   └── og_fetcher.py          # reuse import из ozon_public_scraper
├── parsers/
│   ├── json_ld.py             # reuse import (уже generic, не Ozon-специфичный)
│   ├── og_extractor.py        # reuse import
│   ├── price.py               # reuse import
│   └── adapters/
│       ├── base.py            # Protocol: domain, supports(url), extract(html) -> dict
│       ├── dns_shop.py        # оргтехника — dns-shop.ru
│       ├── citilink.py        # оргтехника — citilink.ru
│       ├── mvideo.py          # оргтехника — mvideo.ru
│       ├── chetyre_tochki.py  # шины — 4tochki.ru
│       ├── koleso.py          # шины — koleso.ru
│       └── lamoda.py          # одежда — lamoda.ru
├── ml/
│   ├── query_classifier.py    # rubert-tiny2 cosine с category prototypes
│   ├── relevance_filter.py    # reuse rubert-tiny2 из ozon_ml_filter
│   └── llm.py                 # dual-mode LLM client (no-op на CPU, реальный на GPU)
├── browser/
│   ├── __init__.py
│   └── fetch.py               # nodriver с собственным semaphore (НЕ ozon_browser_semaphore)
├── jobs/
│   └── build_mini_index.py    # CLI: python -m other_public_scraper.jobs.build_mini_index
└── storage/
    └── meili.py               # обёртка над Meilisearch, индекс other_products

backend/app/sources/other/search.py   # вместо return [] вызывает other_public_scraper
```

---

## Пайплайн запроса — каскад из 5 tier'ов

```
query
  │
  ▼
classify_query(query)
  → category: clothes | tires | orgtech | unknown
  │                       (rubert-tiny2, 20 мс)
  │
  ├─► Meili "other_products" WHERE category=X     → до 10 кандидатов (instant)
  └─► SearXNG live (-site:wb/ozon/yandex.market)  → 15–20 URL
                                  │           │
                    domain blacklist + dedup  │
                                  └───────────┘
                                       │
                          ML cosine(query, snippet_title) → top-8
                                       │
══════════════════════════════════════ TIER 1: FAST PATH (0–8 сек) ══════════════
                    parallel fetch curl_cffi (asyncio.Semaphore(4))
                                       │
                     per-domain adapter → JSON-LD → OG → trafilatura
                                       │
                        price normalize → копейки
                                       │
                                       ▼
                          ┌─ извлечено корректно? ─┐
                          │                        │
                         YES                       NO / SPA / dummy HTML
                          │                        │
                          ▼                        ▼
══════════════════════════ TIER 1.5: LLM-валидатор (только GPU, ~2 сек/страница) ═
              если result серый (нет price       │
              или relevance в зоне 0.3–0.6):     │
              Qwen2.5-3B: "это товар по          │
              запросу X? yes/no"                 │
                          │                        │
                          ▼                        ▼
══════════════════════════ TIER 2: BROWSER FALLBACK (8–12 сек, fire-and-forget) ══
                                       │
                          триггер: HTML < 5KB visible text
                          ИЛИ нет JSON-LD/OG ИЛИ status=blocked
                                       │
                          other_browser_semaphore (НЕ ozon)
                          nodriver → rendered DOM → re-run extruct
                                       │
                          результаты → SearchTaskStore.update_progress
                          (фронт догружает через polling — уже есть)
                                       │
                                       ▼
══════════════════════════ TIER 2.5: LLM-экстрактор (только GPU, ~6 сек/страница) ═
              если и browser ничего не извлёк:    │
              trafilatura → 500 ток cleaned text  │
              Qwen2.5-7B: → JSON {title,price,    │
              image,characteristics}              │
                                       │
                                       ▼
══════════════════════════ TIER 3: BACKGROUND ENRICHMENT (offline, GPU only) ═══
              Celery job по простою:              │
              перебирает Meili-документы          │
              с confidence < 0.7 → дописывает     │
              характеристики через LLM            │
                                       │
                                       ▼
                ML cosine(query, full_title) + regex + price-range sanity
                                       │
                      Meili upsert ("other_products") ← incremental
                                       │
                   Product[] с confidence:
                     adapter      = 1.0
                     json-ld      = 0.8
                     og           = 0.6
                     llm-extract  = 0.5
                     trafilatura  = 0.4
                                       │
                       SearchGroup(source="other")
```

**Latency budget по режимам:**

| Tier | CPU dev | GPU demo |
|------|---------|----------|
| 1: SearXNG + fetch + extract | 6–8 с | 6–8 с |
| 1.5: LLM-валидатор серых | пропуск | +2–4 с (на 2–3 серых) |
| 2: Browser fallback | +10–15 с (fire-and-forget) | +10–15 с (fire-and-forget) |
| 2.5: LLM-экстрактор | пропуск | +6–10 с (на 1–2 совсем сложных) |
| 3: Background | — | offline |

`asyncio.wait_for(timeout=12)` в оркестраторе — Tier 1 (+1.5 на GPU) должны успевать. Tier 2/2.5 завершаются после, апдейтят фронт через polling.

---

## Per-domain адаптеры

### Оргтехника (3 адаптера)

| Домен | Специфика |
|-------|-----------|
| dns-shop.ru | Schema.org Product + `[data-product]` таблица характеристик |
| citilink.ru | Schema.org Product + `product-characteristics__list` |
| mvideo.ru | Schema.org Product + `pdp-characteristics` блок |

### Шины (2 адаптера)

| Домен | Специфика |
|-------|-----------|
| 4tochki.ru | Стандартный Schema.org + доп. характеристики (сезон, R, ширина/профиль) |
| koleso.ru | Schema.org Product + таблица `spec-table`; title часто содержит полный типоразмер |

### Одежда (1 адаптер)

| Домен | Специфика |
|-------|-----------|
| lamoda.ru | Schema.org Product + JSON в `window.__NUXT__`; характеристики из `product-attribute` |

### Generic fallback (все остальные домены)

Каскад без adapter:
1. `extract_product_from_json_ld(html)` — `parsers/json_ld.py` (reuse)
2. OG meta (`og:title`, `og:image`, `product:price:amount`) — `parsers/og_extractor.py` (reuse)
3. `trafilatura.extract` + regex `\d[\d\s]*\s*(?:₽|руб)` для цены

---

## Фильтрация мусора — 3 уровня

### Уровень 1 — Domain blacklist (до fetch)

Отбрасываем из SearXNG-выдачи:
- Маркетплейсы: `ozon.ru`, `wildberries.ru`, `market.yandex.ru`, `avito.ru`, `youla.ru`, `kazanexpress.ru`
- Агрегаторы цен: `price.ru`, `e-katalog.ru`, `market.ru`, `yandex.ru/products`
- Контент: `vc.ru`, `habr.com`, `dtf.ru`, `pikabu.ru`

### Уровень 2 — ML cosine на snippet (до fetch)

```python
# model — уже загружен в ozon_ml_filter
similarity = cosine(encode(query), encode(snippet_title))
keep = similarity >= 0.45
```

Отсекает ~60% мусора без HTTP-запросов.

### Уровень 3 — Санити после extraction

- ML cosine(query, full_title) >= 0.40
- Категориальный regex:
  - шины: `\d{3}/\d{2}\s*R?\d{2}` должен присутствовать в title
  - оргтехника: хотя бы один из брендов (`canon|hp|epson|logitech|acer|lenovo|asus|dell...`)
  - одежда: отсев по keywords (`чехол`, `кейс`, `пленка`, `аксессуар`)
- Price-range sanity: min/max из median WB ± 3× (заполняется после WB отработает параллельно)

---

## Category classifier

```python
# Один раз при старте — warm up model
PROTOTYPES = {
    "orgtech": "ноутбук компьютер принтер монитор клавиатура мышь процессор",
    "tires": "шина резина колесо диск типоразмер летняя зимняя",
    "clothes": "одежда куртка платье ботинки пальто джинсы футболка",
}

def classify_query(query: str) -> str:
    q_emb = model.encode(query)
    scores = {cat: cosine(q_emb, model.encode(proto)) for cat, proto in PROTOTYPES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 0.35 else "unknown"
```

---

## Mini-index (Meilisearch `other_products`)

### Схема документа

```json
{
  "id": "dns-shop.ru::12345",
  "url": "https://dns-shop.ru/product/...",
  "domain": "dns-shop.ru",
  "title": "Ноутбук ASUS VivoBook 15 ...",
  "category": "orgtech",
  "image_url": "https://...",
  "last_price": 6499000,
  "keywords": ["ноутбук", "asus", "vivobook"],
  "confidence": 1.0
}
```

### Pre-crawl скрипт

```bash
python -m other_public_scraper.jobs.build_mini_index \
  --domains dns-shop.ru,citilink.ru,mvideo.ru,4tochki.ru,koleso.ru,lamoda.ru \
  --max-per-domain 250 \
  --categories orgtech,tires,clothes
```

Источник URL — sitemap.xml каждого домена (паттерн из `pipelines/sitemap.py`, параметризуем). Запускается за час до демо командой `make warmup`.

### Incremental

При каждом live-запросе успешно извлечённый Product → `meili.upsert("other_products", ...)`. TTL не ставим (Meilisearch не поддерживает per-document TTL), но цена может устареть — это нормально для демо.

---

## Интеграция в оркестратор

`backend/app/sources/other/search.py`:

```python
from other_public_scraper.scraper import search_other

async def search_other_sources(request: SearchRequest) -> list[Product]:
    return await asyncio.wait_for(
        search_other(request.query, request.region),
        timeout=12.0,   # не блокируем WB/YM
    )
```

Таймаут 12 сек: SearXNG (3с) + parallel fetch 8 URL (4–6с) + ML filter (1с) + margin.

Если timeout — `_safe_search` в оркестраторе уже ловит исключение, группа `other` отдаёт `error="timeout"`.

Tier 2 / 2.5 (browser fallback + LLM-экстрактор) запускаются **в background** через `asyncio.create_task` и пишут результаты в `SearchTaskStore.update_progress` — фронт догружает их при polling'е `/search/{task_id}`. Механизм уже существует для других источников.

---

## Конфигурация (env)

```env
# ───── Always (CPU dev и GPU demo) ─────
SEARXNG_URL=http://localhost:8080
MEILI_URL=http://localhost:7700
MEILI_MASTER_KEY=dev-master-key

OTHER_PRECRAWL_DOMAINS=dns-shop.ru,citilink.ru,mvideo.ru,4tochki.ru,koleso.ru,lamoda.ru
OTHER_PRECRAWL_MAX_PER_DOMAIN=250

OTHER_SEARCH_TIMEOUT_SECONDS=12
OTHER_FETCH_CONCURRENCY=4

OTHER_BROWSER_ENABLED=true                      # Tier 2
OTHER_BROWSER_TIMEOUT_SECONDS=15
# семафор=1, физически отдельный от ozon_browser_semaphore

# ───── GPU demo only ─────
OTHER_LLM_ENABLED=false                         # true на VPS
LLM_ENDPOINT_URL=http://localhost:11434/v1      # Ollama / vLLM
LLM_VALIDATOR_MODEL=qwen2.5:3b-instruct-q4_K_M  # Tier 1.5
LLM_EXTRACTOR_MODEL=qwen2.5:7b-instruct-q4_K_M  # Tier 2.5
LLM_VALIDATOR_TIMEOUT=4
LLM_EXTRACTOR_TIMEOUT=10

# ───── Mini-index enrichment (Celery, GPU only) ─────
OTHER_BACKGROUND_ENRICHMENT_ENABLED=false       # true на VPS
```

---

## Что показываем жюри

1. **Не whitelist, а каскад.** Любой сайт с Schema.org/OG проходит generic путём. Адаптеры — оптимизация точности для частых доменов. Сложные сайты вытягиваются browser-fallback'ом, остаточные — LLM-экстрактором.
2. **Каскадная деградация качества HTML.** Конкретно объясняем 5 tier'ов: «обычные сайты — за 0.5 сек regex; JS-only — браузер; кастомная вёрстка без Schema.org — LLM понимает её как человек». Это техническая глубина, которую жюри ценит.
3. **Dual-mode (CPU/GPU).** Покажем, что система работает даже без GPU (Tier 1+2), а GPU даёт качественный буст (Tier 1.5+2.5). Это про «оптимальное использование ресурсов» из критериев.
4. **Самообучающийся индекс.** Повторный запрос — instant из Meilisearch. Background-pipeline на GPU дообогащает.
5. **Категория-aware routing.** Запросы «летняя резина 205/55 R16» и «принтер hp» — разные адаптеры и domain-наборы.
6. **Кросс-источниковая валидация цены.** Median WB как anchor для sanity-check 4-го.
7. **Динамичность.** Запрос вне трёх категорий — SearXNG live, generic extruct, индекс пополняется в реальном времени.

---

## Риски и митигация

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| SearXNG возвращает 0 (капча Google/DDG) | Средняя | Mini-index всегда отвечает; в SearXNG включить Brave/Mojeek как engines |
| Sitemap закрыт у домена | Средняя | Fallback: категориальная витрина `/catalog/` пагинацией |
| CSS-адаптер сломан (пересборка сайта) | Средняя | Fallback на JSON-LD/OG без адаптера; degrade, не crash |
| Latency > 12 сек | Средняя | `asyncio.wait_for(timeout=12)` → группа с error, остальные источники уже готовы |
| Цена доставки вместо цены товара | Высокая | JSON-LD приоритет (`offers.price` vs текст); контекст-check regex |
| Мусор в выдаче на одежде | Высокая | 3-уровневый фильтр + negative keywords (чехол, кейс, пленка) |
| **LLM не отвечает на демо (упал vLLM, OOM на VPS)** | Средняя | `OTHER_LLM_ENABLED=false` → graceful degrade до baseline; всё работает без LLM |
| **GPU-VPS дороже бюджета / не достали к демо** | Средняя | Baseline на CPU полностью работоспособен; LLM-tier'ы опциональны |
| **Browser fallback конфликтует с Ozon** | Низкая (отдельный семафор) | `other_browser_semaphore` физически отдельный объект, не Ozon-овский |
| **nodriver в browser-fallback падает в SPA с challenge** | Средняя | Try/except, дальше идём по списку URL; не блокируем Tier 1 результаты |
| **LLM-extractor галлюцинирует цены** | Средняя | Жёсткий output schema через JSON mode; price-range sanity после извлечения; confidence=0.5 не вытесняет надёжные источники в ранкере |

---

## Быстрый старт реализации

### Фаза 1 — Baseline (CPU dev, обязательно работает)

1. `git checkout main` + `git pull` (на main уже есть `backend/ozon_public_scraper/`)
2. `cp -r backend/ozon_public_scraper backend/other_public_scraper`
3. `sed -i 's/ozon_public/other_public/g' backend/other_public_scraper/**/*.py`
4. Изменить `pipelines/searxng.py`: убрать `site:ozon.ru`, добавить `-site:wildberries.ru -site:ozon.ru -site:market.yandex.ru`
5. Изменить `pipelines/sitemap.py`: параметризовать `SITEMAP_INDEX_URL` через config, убрать regex `ozon.ru/product/`
6. Добавить `config.py`: `DOMAIN_ADAPTERS`, `BLACKLIST`, `CATEGORY_KEYWORDS`
7. Написать 6 адаптеров (скелет по 30 строк каждый)
8. Написать `ml/query_classifier.py` (~20 строк)
9. Написать `ml/llm.py` с no-op-режимом (`OTHER_LLM_ENABLED=false` по дефолту)
10. Подключить в `backend/app/sources/other/search.py`
11. Запустить `build_mini_index` для pre-crawl

### Фаза 2 — Tier 2: browser fallback

12. `browser/fetch.py` — `other_browser_semaphore = asyncio.Semaphore(1)` (импорт из `app/core/browser_semaphore.py`, отдельный объект)
13. Триггер: `len(visible_text) < 5000` или `extruct` пустой → пробуем браузер
14. `asyncio.create_task` + `SearchTaskStore.update_progress` для асинхронного апдейта фронта

### Фаза 3 — GPU demo enrichment (только если VPS готов)

15. Поднять Ollama/vLLM на VPS, выкачать `qwen2.5:3b-instruct-q4_K_M` и `qwen2.5:7b-instruct-q4_K_M`
16. `OTHER_LLM_ENABLED=true` + `LLM_ENDPOINT_URL=http://...`
17. Включить Tier 1.5 (валидатор серых случаев) в `ml/llm.py::validate`
18. Включить Tier 2.5 (экстрактор) — JSON-mode prompt с schema `{title, price, image_url, characteristics}`
19. (Опционально) Tier 3 — Celery beat job, перебирает Meili-документы с `confidence < 0.7`

### Контрольные точки

| Когда | Что должно работать |
|-------|---------------------|
| После Фазы 1 | Поиск возвращает Product[] из 4-го источника для 3 категорий, CPU only |
| После Фазы 2 | Lamoda/SPA-сайты тоже отдают данные через rendered DOM |
| После Фазы 3 | Долгий хвост сайтов без Schema.org покрыт LLM-экстрактором |

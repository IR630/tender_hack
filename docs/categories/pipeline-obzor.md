# Пайплайн поиска: обзор для нового человека

Как запрос пользователя превращается в список товаров с четырёх источников.

**Код:** `backend/app/orchestrator/search.py` и соседние модули  
**Техническая шпаргалка:** [pipeline.md](pipeline.md)

---

## В двух словах

Пользователь нажимает «Искать» → фронт шлёт запрос на API → бэкенд **параллельно** опрашивает маркетплейсы → собирает один JSON → фронт показывает блоки WB / YM / Ozon / Other.

Ozon идёт **последним**, потому что он медленный (минута+) и занимает единственный Chrome.

---

## Участники (файлы)

```
frontend/App.tsx
      │ POST /search
      ▼
api/routes/search.py          ← создаёт task_id, запускает фоновую задачу
      ▼
tasks/store.py                ← хранит статус «идёт поиск / готово»
      ▼
orchestrator/search.py        ← главный дирижёр
      ├── query/processor.py  ← пока только trim() запроса
      ├── core/regions.py     ← Москва, СПб… → параметры WB/YM
      ├── scrapers/wb.py
      ├── scrapers/yandex_market.py
      ├── sources/other/search.py
      └── scrapers/ozon.py      ← после всех остальных
```

---

## Пошагово

### 1. Старт

API создаёт **`task_id`** (UUID) и сразу отвечает фронту: «вот id, опрашивай статус».

Фронт каждые **3 секунды** делает `GET /search/{task_id}`.

### 2. Предобработка

- **`process_query`** — убирает пробелы по краям. Исправление опечаток пока **не** реализовано.
- **`resolve_region`** — «moscow» → объект с кодами для WB и YM.

### 3. Параллельная волна

Одновременно:

| Источник | Примерное время |
|----------|-----------------|
| Wildberries | 1–3 с |
| Яндекс Маркет | 5–20 с |
| Other | мгновенно (пусто) |

Как только источник готов — его блок **сразу** попадает в ответ polling (partial groups). Пользователь не ждёт Ozon, чтобы увидеть WB.

### 4. Ozon

После parallel-блока — один вызов `ozon.scraper.search`. Может занять **35–180 с**.

### 5. Финал

- Считается **summary**: min / median / max цена по всем товарам (цены в копейках).
- Task store: `status = completed`, полный `SearchResponse`.

---

## `_safe_search` — защита от падений

Если один scraper упал с exception — **весь поиск не ломается**. Для этого источника будет пустой список + текст ошибки в `SearchGroup.error`.

---

## Task Store (`tasks/store.py`)

Простая **память в RAM** сервера (не Redis, не база):

| Поле | Смысл |
|------|-------|
| `status` | pending → running → completed / failed |
| `message` | «Wildberries…», «Ozon: браузер…» |
| `groups` | уже готовые блоки маркетплейсов |
| `result` | полный ответ, когда всё готово |

Задачи старше **1 часа** удаляются. После перезапуска API старые `task_id` не работают.

---

## Query Processor — заглушка

Сейчас только `strip()`. В architecture.md заложены SymSpell, синонимы, Ollama — **не подключены**.

---

## ML Ranker — заглушка

`ml/ranker.py` — post-ranking по `relevance_score`. **Пока не вызывается** из оркестратора, будет подключён для сортировки результатов.

Релевантность внутри Ozon broad search: `ozon_ml_filter.py`.

---

## Scraper Base (`scrapers/base.py`)

Общий интерфейс: у каждого маркетплейса есть `async def search(...) -> list[Product]` и поля `last_error` / `last_source_status` (для Ozon WAF).

---

## Обзоры по маркетплейсам

- [Wildberries](../marketplaces/wildberries-obzor.md)
- [Яндекс Маркет](../marketplaces/yandex-market-obzor.md)
- [Ozon](../marketplaces/ozon-obzor.md)
- [Other](../marketplaces/other-obzor.md)

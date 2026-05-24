# Tender Hack — Price Aggregator

Интеллектуальный сервис агрегации цен с маркетплейсов и открытых источников Рунета.  
Параллельно опрашивает **Wildberries**, **Ozon**, **Яндекс Маркет** и **динамический 4-й источник** через SearXNG.

---

## Содержание

- [Быстрый старт](#быстрый-старт)
- [Архитектура](#архитектура)
- [Источники данных](#источники-данных)
- [API](#api)
- [Конфигурация](#конфигурация)
- [Локальная разработка](#локальная-разработка)
- [Тестирование](#тестирование)
- [Структура монорепо](#структура-монорепо)
- [Документация](#документация)

---

## Быстрый старт

```bash
git clone https://github.com/IR630/tender_hack.git
cd tender_hack
cp .env.example .env

# Гибридный режим: инфра в Docker, API на хосте
cd docker && bash up.sh
```

| Сервис | URL |
|---|---|
| Frontend | http://127.0.0.1:5173 |
| API | http://127.0.0.1:8000 |
| Swagger UI | http://127.0.0.1:8000/docs |
| SearXNG | http://127.0.0.1:8080 |

> **Почему API на хосте?**  
> Playwright/nodriver требует реальный X-дисплей (`DISPLAY=:99`). В гибридном режиме API видит дисплей хоста, а Redis и SearXNG живут в Docker.

Полная инструкция по запуску: [docs/run.md](docs/run.md) · Docker-only: [docs/docker-run.md](docs/docker-run.md)

---

## Архитектура

### Общая схема системы

```mermaid
graph TB
    subgraph Client["Клиент"]
        UI[React SPA<br/>:5173]
    end

    subgraph API["FastAPI — :8000"]
        EP1["POST /search/task"]
        EP2["GET /search/task/{id}"]
        EP3["POST /search (sync)"]
        Store["TaskStore<br/>(in-memory)"]
    end

    subgraph Pipeline["Оркестратор (search.py)"]
        QP["process_query<br/>спеллчек + синонимы"]
        Gather["asyncio.gather"]
    end

    subgraph Sources["Источники (параллельно)"]
        WB["Wildberries<br/>JSON API"]
        YM["Яндекс Маркет<br/>curl_cffi + HTML"]
        OZ["Ozon<br/>Playwright + ML re-rank"]
        OT["4-й источник<br/>SearXNG → Schema.org"]
    end

    subgraph Infra["Инфраструктура"]
        Redis["Redis<br/>кеш 6ч"]
        SearXNG["SearXNG<br/>:8080"]
        ML["rubert-tiny2<br/>ранжирование"]
    end

    UI -->|"POST task_id"| EP1
    UI -->|"GET polling"| EP2
    EP1 -->|"background"| Pipeline
    EP2 --> Store
    Store --> UI

    QP --> Gather
    Gather --> WB & YM & OZ & OT
    WB & YM & OZ & OT -->|"list[Product]"| Gather
    Gather -->|"SearchResponse"| Redis
    Gather -->|"SearchResponse"| Store

    OT --> SearXNG
    OZ --> ML
    WB & YM & OZ & OT <-->|"cache hit/miss"| Redis

    style Client fill:#1e293b,stroke:#334155,color:#e2e8f0
    style API fill:#1e3a8a,stroke:#3b82f6,color:#e2e8f0
    style Pipeline fill:#14532d,stroke:#22c55e,color:#e2e8f0
    style Sources fill:#7c2d12,stroke:#f97316,color:#e2e8f0
    style Infra fill:#4a044e,stroke:#a855f7,color:#e2e8f0
```

### Полный путь поискового запроса

```mermaid
flowchart TB
    User([Клиент]) --> API["POST /search/task\nFastAPI"]
    API --> TaskID[/"Возврат task_id"/]
    API -. "background" .-> Spawn["spawn_search_task"]

    Spawn --> Q["process_query\n━━━━━━━━━━━━━━━\n① локальные расширения\n② Yandex Speller API"]
    Q --> Reg["resolve_region\nDest ID для WB"]
    Reg --> Gather{{"asyncio.gather\n4 источника параллельно"}}

    %% ── Wildberries ──
    Gather --> WB1["Redis cache check\nTTL 6ч"]
    WB1 -->|"hit"| WBDone["cached result"]
    WB1 -->|"miss"| WB2["Warmup\nGET wildberries.ru → cookies"]
    WB2 --> WB3{"Proxy?"}
    WB3 -->|"да"| WB4["Proxy race\n32 IP × 8 раундов\ncurl_cffi"]
    WB3 -->|"нет"| WB5["Direct\nrate-limit 3s"]
    WB4 & WB5 --> WB6["search.wb.ru/v5/search\nJSON API"]
    WB6 --> WB7{"HTTP код"}
    WB7 -->|"429/498/403"| WB8["Circuit breaker\n15 мин cooldown"]
    WB7 -->|"200"| WB9["assemble + image probe\nbasket-NN.wbbasket.ru"]

    %% ── Яндекс Маркет ──
    Gather --> YM1["curl_cffi chrome120\nsession TTL 5 мин"]
    YM1 --> YM2["market.yandex.ru/search\n?text=...&lr=..."]
    YM2 --> YM3{"SmartCaptcha?"}
    YM3 -->|"да"| YM4["вернуть пусто + error"]
    YM3 -->|"нет"| YM5["selectolax\nparse листинга"]
    YM5 --> YM6["ThreadPool ×4\nфетч карточек товара\nспеки + описание"]

    %% ── Ozon ──
    Gather --> OZ1["browser_semaphore\n≤2 одновременно"]
    OZ1 --> OZ2["nodriver\nheadful Chrome, X11 :99"]
    OZ2 --> OZ3["Warmup\nGET ozon.ru → задержка"]
    OZ3 --> OZ4{"WAF challenge?"}
    OZ4 -->|"да"| OZ5["blocked_by_waf\nвернуть пусто"]
    OZ4 -->|"нет"| OZ6["GET /search/?text=...\nbroad 48 карточек"]
    OZ6 --> OZ7["extract\nJSON-LD + DOM"]
    OZ7 --> OZ8["ML re-rank\nrubert-tiny2 cosine\ntop-20"]

    %% ── 4-й источник ──
    Gather --> O1["classify_query\nrubert-tiny2 vs прототипы\ntires / orgtech / clothes"]
    O1 --> O2{{"Параллельно\n3 движка"}}
    O2 --> O3a["SearXNG :8080\nself-hosted"]
    O2 --> O3b["Yahoo Search"]
    O2 --> O3c["DuckDuckGo"]
    O3a & O3b & O3c --> O4["Domain blacklist\nотсев маркетплейсов"]
    O4 --> O5["ML cosine\nпорог 0.45\nотсев без HTTP"]
    O5 --> O6["Parallel fetch\nsemaphore=4, curl_cffi"]
    O6 --> O7{"Adapter?"}
    O7 -->|"специфичный"| O8a["DNS-Shop / Citilink\nM.Video / Lamoda\n4tochki / Koleso"]
    O7 -->|"generic"| O8b["Cascade\nJSON-LD → OG → regex"]
    O8a & O8b --> O9["Sanity check\nпо категории"]
    O9 --> O10["Diversification\n≤2 товара с домена"]

    %% ── Агрегация ──
    WBDone & WB9 & YM6 & OZ8 & O10 --> Agg["Build SearchResponse\n━━━━━━━━━━━━━\ngroups by source\nmin / median / max\nцены в копейках"]
    Agg --> RedisStore[("Redis\nкеш 6ч")]
    Agg --> TaskStore["TaskStore\nstatus = completed"]
    TaskStore --> PollEP(["GET /search/task/{id}\npolling ~3с"])
    PollEP --> User

    classDef src fill:#1e3a8a,stroke:#60a5fa,color:#fff
    classDef gate fill:#7c2d12,stroke:#fb923c,color:#fff
    classDef store fill:#14532d,stroke:#4ade80,color:#fff
    classDef event fill:#0f172a,stroke:#94a3b8,color:#fff
    classDef decision fill:#581c87,stroke:#c084fc,color:#fff
    classDef error fill:#450a0a,stroke:#f87171,color:#fff

    class WB1,WB2,WB4,WB5,WB6,WB9,YM1,YM2,YM5,YM6,OZ2,OZ3,OZ6,OZ7,OZ8,O1,O3a,O3b,O3c,O4,O5,O6,O8a,O8b,O9,O10 src
    class Gather,O2 gate
    class RedisStore,TaskStore store
    class User,PollEP event
    class WB3,WB7,YM3,OZ4,O7 decision
    class WB8,YM4,OZ5 error
```

### Слои данных

```mermaid
graph LR
    subgraph Models["Модели данных (core/models.py)"]
        SR["SearchRequest\nquery · region"]
        SQ["SearchQuery\noriginal · corrected\nsynonyms · took_ms"]
        P["Product\ntitle · price (копейки)\nimage_url · product_url\ncharacteristics · rating\nrelevance_score · confidence"]
        SG["SearchGroup\nsource · display_name\ncount · min_price\ndomains · products\nstatus"]
        SS["SearchSummary\ntotal_found\nmin / median / max price"]
        SResp["SearchResponse\nquery · summary · groups"]
    end

    SR --> SQ
    SQ --> SG
    P --> SG
    SG --> SResp
    SS --> SResp

    style Models fill:#1e293b,stroke:#475569,color:#e2e8f0
```

---

## Источники данных

| Источник | Метод | Антибот | Лимит |
|---|---|---|---|
| **Wildberries** | JSON API (`search.wb.ru`) | Proxy race (32 IP), circuit breaker, rate-limit 3s | 15 товаров |
| **Яндекс Маркет** | `curl_cffi` chrome120 + selectolax HTML | TLS impersonation, сессия 5 мин, Cloudflare Workers | 20 товаров |
| **Ozon** | Playwright + nodriver (headful Chrome) | playwright-stealth, X11 headful, semaphore ≤2, warmup | top-20 после ML re-rank |
| **4-й источник** | SearXNG → curl_cffi → Schema.org | Domain blacklist, ML snippet-фильтр, ≤2 с домена | 10–15 товаров |

### Антибот-слои подробно

```mermaid
graph TD
    subgraph WB["Wildberries"]
        WBR["Rhythm (≥3s между запросами)"]
        WBP["Proxy race\n32 Cloudflare Workers IP"]
        WBC["Circuit breaker\n15 мин cooldown"]
        WBCa["Redis cache 6ч"]
        WBR --> WBP --> WBC --> WBCa
    end

    subgraph YM["Яндекс Маркет"]
        YMT["TLS fingerprint\nchrome120 via curl_cffi"]
        YMS["Сессия-пул\nTTL 5 мин"]
        YMB["Backoff 429\n2→4→8→16s"]
        YMT --> YMS --> YMB
    end

    subgraph OZ["Ozon"]
        OZS["playwright-stealth\nwebdriver=false"]
        OZX["Headful X11 :99\nне headless"]
        OZW["Warmup flow\nглавная → задержка → поиск"]
        OZM["browser_semaphore\n≤2 одновременно"]
        OZS --> OZX --> OZW --> OZM
    end

    subgraph OT["4-й источник"]
        OTB["Domain blacklist\n(маркетплейсы, агрегаторы)"]
        OTM["ML cosine similarity\nпорог 0.45"]
        OTD["Diversification\n≤2 товара с домена"]
        OTB --> OTM --> OTD
    end
```

---

## API

### Эндпоинты

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/search/task` | Создать задачу поиска (async) |
| `GET` | `/search/task/{id}` | Получить статус / результат |
| `POST` | `/search` | Синхронный поиск (dev/debug) |
| `POST` | `/search/mock` | Mock-ответ для UI-тестов |
| `GET` | `/regions` | Список доступных регионов |
| `GET` | `/health` | Проверка живости |
| `GET` | `/health/wb` | Конфигурация WB scraper |
| `GET` | `/wb_metrics` | Метрики производительности WB |
| `GET` | `/images/{path}` | Прокси изображений |

### Polling-flow

```
POST /search/task          → {"task_id": "uuid"}
GET  /search/task/{id}     → {"status": "pending"}   # ~сразу
GET  /search/task/{id}     → {"status": "running", "groups": [...]}  # частичные результаты
GET  /search/task/{id}     → {"status": "completed", "result": {...}}  # готово
```

### Пример ответа

```jsonc
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "result": {
    "query": {
      "original": "ноутбук",
      "corrected": "ноутбук",
      "region": "moscow",
      "synonyms_used": [],
      "took_ms": 4231
    },
    "summary": {
      "total_found": 52,
      "min_price": 2990000,   // копейки → 29 900 ₽
      "median_price": 7450000,
      "max_price": 28990000
    },
    "groups": [
      {
        "source": "wildberries",
        "display_name": "Wildberries",
        "count": 15,
        "min_price": 2990000,
        "status": "complete",
        "products": [
          {
            "title": "Ноутбук ASUS VivoBook 15",
            "price": 4590000,
            "image_url": "https://...",
            "product_url": "https://wildberries.ru/...",
            "characteristics": {"RAM": "16 GB", "SSD": "512 GB"},
            "rating": 4.7,
            "relevance_score": 0.92
          }
        ]
      }
    ]
  }
}
```

---

## Конфигурация

Все настройки читаются из `backend/.env` или `.env` в корне через `pydantic-settings`.

### Ключевые переменные

| Переменная | По умолчанию | Описание |
|---|---|---|
| `SEARCH_ENABLED_SOURCES` | `wildberries,yandex_market,ozon,other` | Активные источники |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Адрес Redis |
| `SEARXNG_URL` | `http://127.0.0.1:8080` | Self-hosted SearXNG |
| `CACHE_TTL_SECONDS` | `21600` | TTL кеша (6 часов) |
| `SCRAPER_TIMEOUT_SECONDS` | `8` | Таймаут для каждого источника |
| `WB_PROXY` | — | Прокси для WB (Cloudflare Worker URL) |
| `WB_PROXY_PARALLEL_ATTEMPTS` | `32` | Параллельных IP в гонке |
| `OZON_USE_BROWSER` | `true` | Включить Playwright для Ozon |
| `OZON_BROWSER_HEADLESS` | `false` | Headless блокируется WAF — не включать! |
| `OZON_TWO_STAGE_ENABLED` | `true` | Двухэтапный поиск (broad + ML) |
| `OZON_BROAD_SEARCH_MAX` | `48` | Кол-во товаров на 1-м этапе |
| `OZON_ML_TOP_K` | `20` | Топ-N после ML re-rank |
| `QUERY_SPELL_ENABLED` | `true` | Коррекция опечаток через Yandex Speller |

---

## Локальная разработка

### Требования

- Python 3.12+, [uv](https://docs.astral.sh/uv/)
- Node.js 20+, pnpm
- Docker (для Redis, SearXNG)
- Linux с X-сервером (для Ozon Playwright)

### Backend

```bash
cd backend

# Установка зависимостей
uv sync

# Запуск с hot-reload
uv run uvicorn app.main:app --reload

# Линтер + форматирование
uv run ruff check .
uv run ruff format .

# Smoke-тест против работающего сервера
uv run python scripts/smoke_search.py
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev       # http://127.0.0.1:5173
pnpm build
```

### Инфраструктура (Docker)

```bash
# Полный стек (Redis, SearXNG, frontend)
cd docker && bash up.sh

# Только инфра (API запускать на хосте)
docker compose -f docker-compose.hybrid.yml up -d

# Остановить всё
docker compose down
```

---

## Тестирование

```bash
cd backend

# Unit-тесты (без сети, ~30s)
uv run pytest

# Один файл
uv run pytest tests/test_wb_scraper.py -v

# Интеграционные тесты (живая сеть)
uv run pytest -m integration

# С логами
uv run pytest -s --log-cli-level=DEBUG
```

**Маркеры:**

| Маркер | Описание |
|---|---|
| `integration` | Требует реального интернета и запущенных сервисов |
| (без маркера) | Unit-тесты, безопасно запускать без сети |

---

## Структура монорепо

```
tender_hack/
├── backend/
│   └── app/
│       ├── api/routes/          # HTTP-эндпоинты (search, regions, images)
│       ├── core/                # config, models, cache, browser_semaphore
│       ├── scrapers/
│       │   ├── wb/              # WB: scraper, session, proxy, circuit, rhythm, assemble
│       │   ├── ozon.py          # Ozon scraper
│       │   ├── ozon_browser.py  # Playwright + nodriver
│       │   ├── two_stage_ozon.py
│       │   ├── ozon_ml_filter.py
│       │   └── yandex_market.py
│       ├── sources/other/       # 4-й источник (SearXNG → Schema.org → vision)
│       ├── query/               # process_query, Yandex Speller
│       ├── ml/                  # rubert-tiny2 ранжировщик
│       ├── orchestrator/        # asyncio.gather, run_search
│       ├── tasks/               # TaskStore (статусы фоновых задач)
│       └── main.py
├── frontend/
│   └── src/
│       ├── components/          # ProductCard, SourceGroup, SearchProgress, RegionSelector
│       ├── types/search.ts      # TypeScript-типы (синхронизировать с models.py)
│       └── App.tsx
├── docker/                      # Docker Compose, Dockerfile.api, Dockerfile.frontend
├── docs/                        # Архитектура, Git Flow, Contributing
└── scripts/                     # smoke_search.py и другие утилиты
```

| Путь | Назначение |
|---|---|
| `backend/app/scrapers/wb/` | Wildberries — JSON API, прокси, circuit breaker |
| `backend/app/scrapers/ozon_browser.py` | Ozon — Playwright stealth |
| `backend/app/scrapers/yandex_market.py` | ЯМ — curl_cffi + selectolax |
| `backend/app/sources/other/` | 4-й источник — SearXNG + Schema.org |
| `backend/app/orchestrator/search.py` | Главная оркестрация (asyncio.gather) |
| `backend/app/query/processor.py` | Нормализация запроса |
| `backend/app/ml/ranker.py` | rubert-tiny2 эмбеддинги |
| `backend/app/core/models.py` | Product, SearchGroup, SearchResponse |
| `backend/app/core/config.py` | Все настройки (60+ параметров) |

---

## Технологический стек

### Backend

| Компонент | Технология |
|---|---|
| Framework | FastAPI + Uvicorn (ASGI) |
| HTTP-клиент | `curl_cffi` (chrome120 TLS impersonation) |
| Браузер | Playwright + `nodriver` + `playwright-stealth` |
| HTML-парсинг | `selectolax` (быстро), `trafilatura` (текст) |
| ML/NLP | `rubert-tiny2` через `sentence-transformers` |
| Кеш | Redis (6ч) + `diskcache` для больших данных |
| Поиск | SearXNG self-hosted |
| Валидация | Pydantic v2 |
| Логирование | `structlog` |
| Retry | `tenacity` |

### Frontend

| Компонент | Технология |
|---|---|
| Framework | React 19 + TypeScript |
| Build | Vite |
| Стили | Tailwind CSS + shadcn/ui |
| Пакеты | pnpm |

### Инфраструктура

| Компонент | Технология |
|---|---|
| Контейнеры | Docker Compose |
| Кеш | Redis 7 Alpine |
| Метапоиск | SearXNG |
| Full-text | MeiliSearch (опционально) |
| CI | GitHub Actions |

---

## Документация

- [Запуск проекта](docs/run.md)
- [Docker-only деплой](docs/docker-run.md)
- [Архитектурные ограничения хакатона](docs/ARCHITECTURE_CONSTRAINTS.md)
- [Git Flow](docs/GITFLOW.md)
- [Contributing](docs/CONTRIBUTING.md)
- [Технические шпаргалки](docs/README.md)
- [Обзоры для новичков](docs/obzor/README.md)
- [Условия задачи](task.md)

---

## Git Flow

Все изменения — **только через Pull Request** в `main`. CI должен пройти + 1 approve.

```
feature/xyz  →  PR  →  main
bugfix/xyz   →  PR  →  main
```

Подробнее: [docs/GITFLOW.md](docs/GITFLOW.md)

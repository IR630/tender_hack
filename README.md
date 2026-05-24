# Tender Hack — Price Aggregator

Интеллектуальный сервис поиска цен с маркетплейсов (WB, Ozon, Яндекс Маркет) и динамических источников Рунета.

## Quick Start

```bash
git clone https://github.com/IR630/tender_hack.git
cd tender_hack
cp .env.example .env
./start_demo.sh
```

**Нужен Docker?** Да, для frontend и инфра (Redis, SearXNG, MeiliSearch). API запускается **на хосте** через [uv](https://docs.astral.sh/uv/) — так Ozon browser работает на обычном Linux с экраном.

Подробная инструкция: [docs/run.md](docs/run.md) · Docker-only: [docs/docker-run.md](docs/docker-run.md)

- **Frontend:** http://127.0.0.1:5173
- **API:** http://127.0.0.1:8000
- **API docs:** http://127.0.0.1:8000/docs
- **SearXNG:** http://127.0.0.1:8080

## Локальная разработка

```bash
# Backend
cd backend && uv sync && uv run uvicorn app.main:app --reload

# Frontend (в другом терминале)
cd frontend && pnpm install && pnpm dev
```

## Структура monorepo

| Путь | Назначение | Владелец |
|---|---|---|
| `frontend/` | React UI | Dev 1 |
| `backend/app/scrapers/` | WB, Ozon, Яндекс Маркет | Dev 2 |
| `backend/app/sources/` | 4-й динамический источник | Dev 3 |
| `backend/app/api/`, `query/`, `ml/`, `orchestrator/` | API, ML, оркестрация | Dev 4 |
| `docker/` | Docker Compose, инфра | все |
| `docs/` | Git Flow, contributing | все |

## Как работает поиск

Полный путь запроса от клиента до ответа: обработка запроса (опечатки + синонимы), параллельный опрос четырёх источников через `asyncio.gather`, антибот-слои и кеш на каждом канале, сборка ответа и polling результата.

```mermaid
flowchart TB
    User([Клиент]) --> API[POST /search<br/>FastAPI]
    API --> TaskID[/Возврат task_id/]
    API -.background.-> Spawn[spawn_search_task]

    Spawn --> Q[process_query<br/>━━━<br/>1 локальные расширения<br/>'комп' → 'компьютер'<br/>2 Yandex HTML scrape<br/>curl_cffi → 'Исправлена опечатка']
    Q --> Reg[resolve_region]
    Reg --> Gather{{asyncio.gather }}

    %% ───── Wildberries ─────
    Gather --> WB1[Cache check<br/>Redis 6ч]
    WB1 -->|hit| Done1[return]
    WB1 -->|miss| WB2[Warmup<br/>GET wildberries.ru<br/>GET /catalog/...<br/>сбор cookies]
    WB2 --> WB3{Proxy?}
    WB3 -->|yes| WB4[Proxy-race<br/>32 параллельных IP<br/>up to 8 раундов]
    WB3 -->|no| WB5[Direct rate-limit<br/>3 сек между запросами]
    WB4 --> WB6[search.wb.ru/v4/search<br/>JSON API]
    WB5 --> WB6
    WB6 --> WB7{HTTP?}
    WB7 -->|429/498/403| WB8[Circuit breaker<br/>15 мин cooldown]
    WB7 -->|200| WB9[assemble + image probe<br/>basket-NN.wbbasket.ru]

    %% ───── Яндекс Маркет ─────
    Gather --> YM1[curl_cffi Chrome 120<br/>session 5 мин TTL]
    YM1 --> YM2[market.yandex.ru/search?text=...]
    YM2 --> YM3{SmartCaptcha?}
    YM3 -->|да| YM4[вернуть пусто + error]
    YM3 -->|нет| YM5[selectolax parse листинга]
    YM5 --> YM6[ThreadPool x4<br/>fetch product cards<br/>спеки + описание]

    %% ───── Ozon ─────
    Gather --> OZ1[browser_semaphore]
    OZ1 --> OZ2[nodriver.start<br/>headful, X11 ':99']
    OZ2 --> OZ3[Warmup<br/>GET ozon.ru]
    OZ3 --> OZ4{WAF challenge?}
    OZ4 -->|да| OZ5[blocked_by_waf<br/>вернуть пусто]
    OZ4 -->|нет| OZ6[GET /search/?text=...<br/>broad 48 карточек]
    OZ6 --> OZ7[extract_broad_search<br/>JSON-LD + DOM]
    OZ7 --> OZ8[ML re-rank<br/>rubert-tiny2 cosine<br/>top-20]

    %% ───── 4-й источник ─────
    Gather --> O1[classify_query<br/>rubert-tiny2 vs прототипы<br/>orgtech / tires / clothes / unknown]
    O1 --> O2{{Параллельно<br/>3 движка}}
    O2 --> O3a[SearXNG self-hosted<br/>:8080]
    O2 --> O3b[Yahoo search]
    O2 --> O3c[DuckDuckGo]
    O3a --> O4[Domain blacklist<br/>отсев маркетплейсов<br/>и агрегаторов]
    O3b --> O4
    O3c --> O4
    O4 --> O5[ML cosine snippet<br/>порог 0.45<br/>отсев ~60% без HTTP]
    O5 --> O6[Parallel fetch<br/>semaphore=4<br/>curl_cffi]
    O6 --> O7{Per-domain adapter?}
    O7 -->|есть| O8a[DNS-Shop / Citilink<br/>M.Video / Notik<br/>4tochki / Koleso / Lamoda]
    O7 -->|нет| O8b[Generic cascade<br/>JSON-LD → OG → regex]
    O8a --> O9[Sanity по категории<br/>шины: 205/55R16<br/>оргтехника: бренды]
    O8b --> O9
    O9 --> O10[Diversification<br/>≤2 товара с домена]
    O10 --> O11[(Meilisearch upsert<br/>incremental cache)]

    %% ───── Aggregation ─────
    WB9 --> Agg
    YM6 --> Agg
    OZ8 --> Agg
    O11 --> Agg
    Done1 --> Agg

    Agg[Build SearchResponse<br/>━━━<br/>groups by source<br/>summary: min / median / max<br/>в копейках] --> Store[(Redis cache 6ч)]
    Store --> PollEP([GET /search/task_id<br/>polling 3 сек])
    PollEP --> User

    classDef src fill:#1e3a8a,stroke:#60a5fa,color:#fff
    classDef gate fill:#7c2d12,stroke:#fb923c,color:#fff
    classDef store fill:#14532d,stroke:#4ade80,color:#fff
    classDef event fill:#0f172a,stroke:#94a3b8,color:#fff
    classDef decision fill:#581c87,stroke:#c084fc,color:#fff
    class WB1,WB2,WB4,WB5,WB6,WB9,YM1,YM2,YM5,YM6,OZ2,OZ3,OZ6,OZ7,OZ8,O1,O3a,O3b,O3c,O4,O5,O6,O8a,O8b,O9,O10 src
    class Gather,O2 gate
    class Store,O11 store
    class User,PollEP event
    class WB3,WB7,YM3,OZ4,O7 decision
```

## Git Flow

Все изменения — **только через Pull Request** в `main`. CI должен пройти + 1 approve.

Подробнее: [docs/GITFLOW.md](docs/GITFLOW.md)

## Документация

- [**Документация**](docs/README.md) — технические шпаргалки
- [**Обзоры для новичков**](docs/obzor/README.md) — простым языком
- [Архитектура (набросок)](architecture.md)
- [Условия хакатона](task.md)
- [Contributing](docs/CONTRIBUTING.md)
- [Ограничения хакатона](docs/ARCHITECTURE_CONSTRAINTS.md)
- [Запуск проекта](docs/run.md)
- [Docker-only](docs/docker-run.md)

## Стек

- **Backend:** FastAPI, uv, Redis
- **Frontend:** React, Vite, Tailwind
- **Infra:** Docker Compose, SearXNG, GitHub Actions CI

# Contributing

## Быстрый старт

### Требования

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 22+
- [pnpm](https://pnpm.io/) (`corepack enable`)
- Docker + Docker Compose

### Локальный запуск (без Docker)

**Backend:**

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend:**

```bash
cd frontend
pnpm install
pnpm dev
```

Frontend: http://localhost:5173  
Backend API: http://localhost:8000  
Health check: http://localhost:8000/health

### Запуск полного стенда (рекомендуется)

```bash
cp .env.example .env
./start_demo.sh
```

Docker поднимает frontend и инфра; API — на хосте через `uv`. Подробно: [run.md](run.md).

### Запуск через Docker (весь стек в контейнерах)

```bash
cp .env.example .env
docker compose -f docker/docker-compose.yml up --build
```

Ozon browser в этом режиме часто блокируется — см. [docker-run.md](docker-run.md) или `./docker/up.sh`.

- Frontend: http://localhost:5173
- API: http://localhost:8000
- SearXNG: http://localhost:8080
- Redis: localhost:6379

## Структура проекта

```
backend/app/
  api/           # REST endpoints
  core/          # config, shared models
  scrapers/      # WB, Ozon, Yandex Market
  sources/       # 4-й динамический источник
  query/         # опечатки, синонимы
  ml/            # ranker (post-ranking результатов)
  orchestrator/  # параллельный опрос источников

frontend/src/
  components/    # UI-компоненты
  types/         # TypeScript типы (позже — автоген из OpenAPI)
```

## Как делать PR

1. Прочитайте [GITFLOW.md](./GITFLOW.md)
2. Создайте ветку `feature/<module>-<desc>` от `main`
3. Внесите изменения только в свой модуль (если возможно)
4. Прогоните lint и tests локально
5. Откройте PR → дождитесь CI + approve

## Контракт между модулями

- Общая модель: `backend/app/core/models.py` (`Product`, `SearchResponse`)
- Каждый scraper реализует `BaseScraper` и возвращает `list[Product]`
- Оркестратор (`orchestrator/search.py`) собирает результаты параллельно
- API не знает деталей парсинга — только вызывает оркестратор

## Ограничения хакатона

См. [ARCHITECTURE_CONSTRAINTS.md](./ARCHITECTURE_CONSTRAINTS.md).

# Tender Hack — Price Aggregator

Интеллектуальный сервис поиска цен с маркетплейсов (WB, Ozon, Яндекс Маркет) и динамических источников Рунета.

## Quick Start

```bash
git clone https://github.com/IR630/tender_hack.git
cd tender_hack
cp .env.example .env
docker compose -f docker/docker-compose.yml up --build
```

Подробная инструкция: [docs/docker-run.md](docs/docker-run.md)

- **Frontend:** http://localhost:5173
- **API:** http://localhost:8000
- **API docs:** http://localhost:8000/docs
- **SearXNG:** http://localhost:8080

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

## Git Flow

Все изменения — **только через Pull Request** в `main`. CI должен пройти + 1 approve.

Подробнее: [docs/GITFLOW.md](docs/GITFLOW.md)

## Документация

- [**Документация (маркетплейсы + категории)**](docs/README.md)
- [Архитектура (набросок)](architecture.md)
- [Условия хакатона](task.md)
- [Contributing](docs/CONTRIBUTING.md)
- [Ограничения хакатона](docs/ARCHITECTURE_CONSTRAINTS.md)
- [Запуск через Docker](docs/docker-run.md)

## Стек

- **Backend:** FastAPI, uv, Redis
- **Frontend:** React, Vite, Tailwind
- **Infra:** Docker Compose, SearXNG, GitHub Actions CI

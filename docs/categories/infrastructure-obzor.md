# Инфраструктура и запуск: обзор для нового человека

Docker, регионы, демо со Ozon на хосте.

**Запуск:** [run.md](../run.md) · **Технически:** [infrastructure.md](infrastructure.md), [docker-run.md](../docker-run.md)

---

## Из чего состоит стенд

| Сервис | Порт | Зачем |
|--------|------|-------|
| **API** (FastAPI) | 8000 | Поиск, scrapers |
| **Frontend** (nginx + React) | 5173 | UI |
| **Redis** | 6379 | Кэш WB/YM |
| **SearXNG** | 8080 | Поиск URL (Ozon public, future Other) |
| **MeiliSearch** | 7700 | Индекс URL Ozon public |

---

## Как запустить (одна команда)

```bash
cp .env.example .env
./start_demo.sh
```

**Docker нужен** для frontend и инфра (Redis, SearXNG, MeiliSearch). **API — на хосте** (нужен [uv](https://docs.astral.sh/uv/)), чтобы Ozon browser видел нормальный экран (`DISPLAY=:0`).

Подробно: [run.md](../run.md)

| Режим | Когда |
|-------|-------|
| `./start_demo.sh` | демо, хакатон, проверка Ozon — **по умолчанию** |
| `./docker/up.sh` | весь стек в Docker, но X11 с хоста |
| `docker compose … up` | CI / сервер без Ozon browser |

UI: http://127.0.0.1:5173 · API: http://127.0.0.1:8000

---

## Регионы (`core/regions.py`)

Пользователь выбирает город — scrapers получают разные коды:

| Город | Wildberries (`dest`) | Yandex (`yandex_gid`) |
|-------|----------------------|------------------------|
| Москва | -1257786 | 213 |
| СПб | -1198059 | 2 |
| … | … | … |

Ozon browser регион **не** меняет (пока).

API: `GET /regions`.

---

## Browser Semaphore

**Файл:** `core/browser_semaphore.py`

Одновременно только **один** Chrome для Ozon. Второй запрос ждёт в очереди.

Если Chrome «завис» после сбоя:

```bash
./kill_zombies.sh
```

---

## CI (GitHub Actions)

На каждый PR:

- backend: `uv sync`, ruff, pytest  
- frontend: lint, build  

---

## Локальная разработка без Docker

```bash
# терминал 1
cd backend && uv sync && uv run uvicorn app.main:app --reload

# терминал 2
cd frontend && pnpm dev
```

Нужен Redis локально, если включён кэш WB/YM.

---

## Типичные проблемы

| Проблема | Решение |
|----------|---------|
| Порт 8000 занят | `fuser -k 8000/tcp` |
| Ozon «доступ ограничен» | hybrid demo, warmup, не Docker API |
| Зависший Chromium | `./kill_zombies.sh` |

---

## Env

Скопируйте `.env.example` → `.env` перед запуском.

Для Ozon demo минимум:

```env
OZON_USE_BROWSER=true
DISPLAY=:0
```

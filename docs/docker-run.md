# Запуск проекта через Docker

> **Рекомендуемый способ для команды:** [run.md](run.md) — `./start_demo.sh` (гибрид: Docker + API на хосте, Ozon работает).
>
> Эта страница — когда нужен **весь стек в контейнерах** (CI, сервер, эксперименты).

## Требования

- Docker Engine 24+
- Docker Compose v2 (`docker compose`)
- ~4 GB свободной RAM (API с Chromium + ML-модель rubert)

---

## Быстрый старт (весь стек в Docker)

**Linux с графической сессией (рекомендуется для Ozon):**

```bash
git clone https://github.com/IR630/tender_hack.git
cd tender_hack
git checkout feature/ozon
cp .env.example .env
./docker/up.sh
```

Скрипт `./docker/up.sh` пробрасывает **X11 с хоста** в контейнер API — Ozon работает так же, как в `./start_demo.sh`.

**Без X11 (сервер / CI):**

```bash
DISPLAY=:99 docker compose -f docker/docker-compose.yml up --build
```

Ozon может блокироваться WAF в чистом Xvfb-режиме. WB и Яндекс Маркет работают.

Первый запуск может занять 5–15 минут: сборка frontend, скачивание образов, загрузка ML-модели при первом поиске Ozon.

### Адреса

| Сервис | URL |
|--------|-----|
| UI | http://localhost:5173 |
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| Health | http://localhost:8000/health |
| SearXNG | http://localhost:8080 |
| MeiliSearch | http://localhost:7700 |

Frontend проксирует API: запросы с UI идут на `/api/…` → nginx → `127.0.0.1:8000`.

### Проверка

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

---

## Остановка

```bash
# В терминале, где запущен compose — Ctrl+C

# Или из другого терминала:
docker compose -f docker/docker-compose.yml down

# С удалением volumes (Redis, Meili, disk cache Ozon):
docker compose -f docker/docker-compose.yml down -v
```

---

## Что поднимается

`docker/docker-compose.yml`:

| Контейнер | Порт | Назначение |
|-----------|------|------------|
| `api` | 8000 | FastAPI + scrapers + nodriver (Xvfb `:99`) |
| `frontend` | 5173 | nginx + собранный React |
| `redis` | 6379 | кеш WB / YM |
| `searxng` | 8080 | поиск для Ozon public scraper |
| `meilisearch` | 7700 | индекс Ozon public scraper |

Compose использует `network_mode: host` — сервисы слушают порты напрямую на хосте (удобно при VPN/tun).

---

## Переменные окружения

Скопируйте `.env.example` → `.env` и при необходимости измените:

```env
MEILI_MASTER_KEY=dev-master-key
OZON_USE_BROWSER=true
OZON_BROWSER_CACHE_ENABLED=false
OZON_TWO_STAGE_ENABLED=true
```

Переменные для сервиса `api` задаются в `docker/docker-compose.yml` (секция `environment`).

---

## Ozon в Docker

Ozon требует **настоящий Chromium с DISPLAY**, а не изолированный Xvfb.

| Режим | Ozon | Команда |
|-------|------|---------|
| **X11 с хоста** | ✅ | `./docker/up.sh` |
| Xvfb внутри контейнера (`:99`) | ❌ WAF | `DISPLAY=:99 docker compose …` |
| Гибрид (API на хосте) | ✅ | `./start_demo.sh` |

Перед `./docker/up.sh` на Linux может понадобиться:

```bash
xhost +local:docker
export DISPLAY=:0
```

Compose монтирует `/tmp/.X11-unix` и передаёт `DISPLAY` из окружения.

---

## Типичные проблемы

### Порт уже занят

```bash
# Пример для API
fuser -k 8000/tcp

docker compose -f docker/docker-compose.yml up --build
```

### API не стартует / healthcheck падает

```bash
docker compose -f docker/docker-compose.yml logs api --tail 100
```

Частые причины: не хватает RAM, первый запуск Chromium в контейнере.

### Ozon — «сайт блокирует»

1. Запускайте через `./docker/up.sh` (X11 с хоста), не через чистый Xvfb
2. Проверьте: `echo $DISPLAY` → `:0` или `:1`
3. `xhost +local:docker`
4. Fallback: `./start_demo.sh` (гибрид)

### Пересборка после изменений кода

```bash
docker compose -f docker/docker-compose.yml up --build
```

Только API:

```bash
docker compose -f docker/docker-compose.yml up --build api
```

---

## Запуск в фоне

```bash
docker compose -f docker/docker-compose.yml up --build -d
docker compose -f docker/docker-compose.yml ps
docker compose -f docker/docker-compose.yml logs -f api
```

---

## Локальная разработка без Docker

```bash
# Backend
cd backend && uv sync && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend (другой терминал)
cd frontend && pnpm install && pnpm dev
```

Инфра (Redis, SearXNG) при этом можно поднять отдельно:

```bash
docker compose -f docker-compose.hybrid.yml up -d
```

Этот compose **без API** — только frontend + redis + searxng + meilisearch.

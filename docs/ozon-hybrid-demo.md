# Гибридный демо-стенд (Ozon на хосте)

Ozon с nodriver требует реальный Chromium и графическую сессию. В Docker (Xvfb)
WAF блокирует запросы. Решение — **гибрид**: инфраструктура в Docker, API на хосте.

## Запуск

```bash
./start_demo.sh
```

Скрипт:

1. Поднимает Docker: frontend, Redis, SearXNG, MeiliSearch (`docker-compose.hybrid.yml`)
2. Запускает uvicorn на хосте на `:8000` с `DISPLAY=:0` (или через `xvfb-run`, если DISPLAY не задан)

## URL

| Сервис | Адрес |
|--------|-------|
| UI | http://127.0.0.1:5173 |
| API | http://127.0.0.1:8000 |
| Health | http://127.0.0.1:8000/health |

## Остановка

`Ctrl+C` в терминале со `start_demo.sh` — останавливает API и `docker compose down`.

При зависших процессах Chromium:

```bash
./kill_zombies.sh
```

## Переменные окружения (дефолты в start_demo.sh)

- `OZON_USE_BROWSER=true`
- `OZON_BROWSER_MAX_RETRIES=1`
- `OZON_BROWSER_WARMUP_HOME=true`
- `OZON_ENRICH_WAIT_SECONDS=15`
- `OZON_PIPELINE_TIMEOUT_SECONDS=180`
- `OZON_BROWSER_CACHE_ENABLED=false`

## Типичные проблемы

| Симптом | Причина | Решение |
|---------|---------|---------|
| `address already in use :8000` | Старый uvicorn | `fuser -k 8000/tcp` и перезапуск |
| Ozon «сайт блокирует» на первом запросе | Cold start без warmup | `OZON_BROWSER_WARMUP_HOME=true`, retry |
| Описание только у 1 из 5 | SPA не догрузилась | `OZON_ENRICH_WAIT_SECONDS=15`, одна сессия браузера |
| UI недоступен | Docker не запущен | `docker compose -f docker-compose.hybrid.yml up -d` |

## Production vs demo

Для production Ozon-скraper логично вынести на отдельный сервер с Chromium.
Текущий гибридный режим — для локальной демонстрации на хакатоне.

# Библиотеки: обзор для нового человека

Какие внешние пакеты используем и **зачем**, без версий и pip-магии.

**Файл зависимостей:** `backend/pyproject.toml`, `frontend/package.json`  
**Техническая шпаргалка:** [libraries.md](libraries.md)

---

## Backend — по задачам

### Веб-сервер

| Пакет | Зачем |
|-------|-------|
| **fastapi** | HTTP API, роуты, валидация |
| **uvicorn** | Запускает FastAPI |
| **pydantic** | Модели JSON (Product, SearchResponse…) |

### «Притвориться браузером» в HTTP

| Пакет | Где используется |
|-------|------------------|
| **curl_cffi** | Wildberries JSON, Yandex Market HTML |
| **httpx** | SearXNG в Ozon public |

Обычный `requests` WB часто блокирует — нужен TLS fingerprint Chrome.

### Разбор HTML

| Пакет | Где |
|-------|-----|
| **selectolax** | Yandex Market, парсинг страниц Ozon |

### Настоящий браузер

| Пакет | Где |
|-------|-----|
| **nodriver** | Ozon (основной путь) — Chrome без webdriver-флага |
| **playwright** | Yandex Market — только если curl не сработал |

### ML

| Пакет | Где |
|-------|-----|
| **sentence-transformers** | Ozon: отбор 5 товаров по смыслу запроса |
| **torch** | Движок для sentence-transformers (CPU) |
| **pandas** | Сортировка scores в Ozon ML filter |

### Кэш и поиск

| Пакет | Где |
|-------|-----|
| **redis** | Кэш WB/YM; async кэш Ozon public |
| **diskcache** | Опциональный disk-кэш Ozon browser |
| **meilisearch-python-sdk** | Индекс URL для Ozon public |

### Прочее

| Пакет | Зачем |
|-------|-------|
| **structlog** | JSON-логи Ozon browser |
| **tenacity** | Повторы при загрузке OG Ozon public |

---

## Frontend

| Пакет | Зачем |
|-------|-------|
| **react** | UI |
| **vite** | Сборка и dev-сервер |
| **typescript** | Типы |
| **tailwindcss** | Стили |

---

## Docker-образы (не pip)

- **redis** — кэш  
- **searxng** — meta-search  
- **meilisearch** — полнотекстовый индекс  

---

## Шпаргалка «кто чем ходит на маркетплейсы»

```
Wildberries     → curl_cffi → JSON
Yandex Market   → curl_cffi → HTML → (playwright если надо)
Ozon            → nodriver → Chrome
Ozon public     → httpx + meilisearch
Other           → пока ничего
```

---

## Установка

```bash
cd backend && uv sync
cd frontend && pnpm install
playwright install chromium   # только для YM fallback
```

Torch ставится CPU-версией через uv (см. `pyproject.toml`).

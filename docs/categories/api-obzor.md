# HTTP API: обзор для нового человека

Как фронт общается с бэкендом.

**Код:** `backend/app/main.py`, `backend/app/api/routes/`  
**Техническая шпаргалка:** [api.md](api.md)

---

## В двух словах

Бэкенд — **FastAPI** приложение на порту **8000**. Фронт ходит не напрямую, а через прокси `/api/...` (Vite в dev, nginx в Docker).

Поиск **асинхронный**: сначала «начали», потом опрос «готово ли».

---

## Главные адреса

| URL | Что делает |
|-----|------------|
| `GET /health` | Жив ли сервер (`{"status":"ok"}`) |
| `GET /regions` | Список городов для селектора |
| `POST /search` | Начать поиск → `{ "task_id": "..." }` |
| `GET /search/{task_id}` | Статус + частичные/полные результаты |

Документация Swagger: http://localhost:8000/docs

---

## Как работает поиск (для фронта)

```
1. POST /search
   Body: { "query": "iphone", "region": "moscow" }
   Ответ: { "task_id": "uuid..." }

2. GET /search/uuid...  (сразу и каждые 3 сек)
   Ответ пока идёт работа:
   {
     "status": "running",
     "message": "Яндекс Маркет…",
     "groups": [ ... уже готовые WB, YM ... ]
   }

3. Когда status === "completed":
   {
     "status": "completed",
     "result": { query, summary, groups }
   }
```

Если `status === "failed"` — в `error` текст причины.

---

## Dev-эндпоинты (скрыты из Swagger)

| URL | Зачем |
|-----|-------|
| `POST /search/sync` | Ждать весь поиск в одном запросе (отладка) |
| `POST /search/mock` | Пустой скелет ответа |

---

## Файлы

| Файл | Роль |
|------|------|
| `main.py` | Создаёт app, подключает роуты, health |
| `api/routes/search.py` | `/search`, task_id, polling |
| `api/routes/regions.py` | `/regions` |

---

## Связь с другими частями

- `search.py` создаёт задачу в **task store** и вызывает **orchestrator**.
- Модели запроса/ответа — в **models.py** (Pydantic).

---

## Прокси фронта

**Разработка:** Vite переписывает `/api/search` → `http://localhost:8000/search`

**Docker:** nginx отдаёт React и проксирует `/api/` на API.

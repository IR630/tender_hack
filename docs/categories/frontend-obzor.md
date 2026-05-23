# Frontend: обзор для нового человека

Что видит пользователь и как React ходит к API.

**Код:** `frontend/`  
**Техническая шпаргалка:** [frontend.md](frontend.md)

---

## В двух словах

Одностраничное приложение: поле поиска, выбор города, кнопка «Искать», блоки товаров по маркетплейсам.

Стек: **React 19 + Vite + TypeScript + Tailwind**.

---

## Главный сценарий (`App.tsx`)

```
1. Пользователь вводит запрос, выбирает регион
2. POST /api/search → получаем task_id
3. Каждые 3 сек GET /api/search/{task_id}
4. Пока status === "running" — показываем loader + message ("Wildberries…")
5. groups обновляются по мере готовности источников
6. status === "completed" — показываем summary (min/median/max)
```

Регион сохраняется в **localStorage** (`RegionSelector.tsx`).

---

## Компоненты

| Файл | Что на экране |
|------|----------------|
| `App.tsx` | Форма, polling, сводка цен |
| `SourceGroup.tsx` | Заголовок «Wildberries», список карточек, ошибка источника |
| `ProductCard.tsx` | Картинка, название, цена (÷100), раскрывающееся описание |
| `RegionSelector.tsx` | Dropdown городов |
| `SearchLoader.tsx` | Анимация «ищем…» + текст статуса с бэка |

---

## Порядок блоков на экране

```typescript
["wildberries", "yandex_market", "ozon", "other"]
```

API может отдать groups в другом порядке — фронт **пересортировывает**.

---

## Особый случай: Ozon WAF

Если `group.status === "blocked_by_waf"` — `SourceGroup` показывает предупреждение вместо пустого молчания.

---

## Типы (`types/search.ts`)

Копия полей бэкенда (`Product`, `SearchResponse`, …). При изменении API нужно синхронизировать **оба** файла.

---

## Запуск локально

```bash
cd frontend && pnpm install && pnpm dev
```

Откроется http://localhost:5173 — запросы `/api/*` уйдут на бэкенд :8000.

---

## Production

Собранный статик кладётся в Docker-образ с **nginx**, который проксирует API.

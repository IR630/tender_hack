# Frontend

**Код:** `frontend/`

## Стек

React 19, Vite 6, TypeScript 5.7, Tailwind 3, pnpm.

## Поток поиска

```
handleSearch
  POST /api/search { query, region }
  pollTask(task_id) immediately
  setInterval(pollTask, 3000ms)
  until completed | failed
```

### Partial results

Каждый poll обновляет `groups` — пользователь видит WB/YM до завершения Ozon.

### Порядок источников в UI

```typescript
SOURCE_ORDER = ["wildberries", "yandex_market", "ozon", "other"]
```

API отдаёт groups в другом порядке — frontend re-sort через `orderGroups()`.

## Компоненты

| Файл | Роль |
|------|------|
| `App.tsx` | Form, polling, summary |
| `SourceGroup.tsx` | Блок маркетплейса; WAF banner для `blocked_by_waf` |
| `ProductCard.tsx` | Цена ÷100, expandable description |
| `RegionSelector.tsx` | Dropdown + localStorage |
| `SearchLoader.tsx` | Loading + status message |

## Types

`types/search.ts` — mirrors backend Pydantic:

- `Product`, `SearchGroup`, `SearchResponse`
- `SearchTaskStatusResponse`
- `SEARCH_POLL_INTERVAL_MS = 3000`

## Proxy

- **Dev:** Vite `/api` → `localhost:8000`
- **Prod:** nginx static + `/api/` proxy

## Цены

Backend хранит **копейки** → `ProductCard` делит на 100 для рублей.

## Ozon WAF

`SourceGroup` — отдельная плашка при `group.status === "blocked_by_waf"`.

## Связанные категории

- [api.md](api.md)
- [models.md](models.md)
- [pipeline.md](pipeline.md)

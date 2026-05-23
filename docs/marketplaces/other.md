# Другие источники (4-й маркетплейс)

**Код:** `backend/app/sources/other/search.py`  
**source:** `other`

## Идея

Placeholder для **динамического 4-го источника** — поиск по Runet (не WB/Ozon/YM). Описан в `architecture.md`, в коде пока stub.

## Текущий пайплайн

```
SearchRequest
    │
    ▼
resolve_region(request.region)   # регион резолвится, но не используется
    │
    ▼
return []                        # всегда пустой список
```

Оркестратор создаёт `SearchGroup(source="other", count=0)` без error.

## Планируемый обход (architecture.md)

```
query
  │
  ▼
SearXNG (general web, не site:ozon.ru)
  │
  ▼
Schema.org / JSON-LD product extraction
  │
  ▼
Vision model (fallback — цена на скриншоте)
  │
  ▼
Product[] с dynamic source_domain
```

## Infra уже есть

SearXNG поднят в Docker (`docker/searxng/settings.yml`) — сейчас используется **Ozon public scraper**, не other.

Meilisearch — тоже для Ozon index.

## Место в общем пайплайне

- Запуск **parallel** с WB и YM
- В API groups порядок: `other` перед `ozon`
- В UI (`App.tsx`): `other` последний в `SOURCE_ORDER`

## Библиотеки (future)

- httpx — SearXNG client (как в `ozon_public_scraper/pipelines/searxng.py`)
- selectolax / extruct — Schema.org
- vision model — TBD

## Связанные документы

- [../categories/pipeline.md](../categories/pipeline.md)
- [ozon.md](ozon.md) — SearXNG reuse pattern
- [../../architecture.md](../../architecture.md)

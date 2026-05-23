# Доменные модели

**Код:** `backend/app/core/models.py`  
**Frontend mirror:** `frontend/src/types/search.ts`

## Product

Единый формат товара от всех scrapers.

```python
source: "wildberries" | "ozon" | "yandex_market" | "other"
source_domain: str
title: str
description: str = ""
price: int              # КОПЕЙКИ — UI делит на 100
currency: str = "RUB"
image_url: str
product_url: str
characteristics: dict[str, str]
rating: float | None
reviews_count: int | None
relevance_score: float = 0.0
confidence: float = 1.0
```

## SearchGroup

Результаты одного маркетплейса:

| Поле | Описание |
|------|----------|
| source | id источника |
| display_name | «Wildberries», «Ozon»… |
| count | len(products) |
| min_price | min в группе |
| domains | уникальные source_domain |
| products | list[Product] |
| error | текст ошибки scraper |
| status | `"blocked_by_waf"` для Ozon |

## SearchResponse

```python
query: SearchQuery       # metadata
summary: SearchSummary   # min/median/max по всем источникам
groups: list[SearchGroup]
```

## SearchQuery

```python
original, corrected: str
region, region_name: str
synonyms_used: list[str]
took_ms: int
```

## SearchSummary

```python
total_found: int
min_price, median_price, max_price: int | None
```

## Task models

```python
SearchRequest(query, region="moscow")
SearchTaskCreateResponse(task_id)
SearchTaskStatusResponse(task_id, status, message, error, result, groups)
```

## Библиотеки

pydantic v2 — validation, JSON serialization

## Маркетплейсы

Как scrapers заполняют поля: [../marketplaces/README.md](../marketplaces/README.md)

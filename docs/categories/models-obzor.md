# Модели данных: обзор для нового человека

Какие «формы» JSON ходят между бэкендом и фронтом.

**Код:** `backend/app/core/models.py`, `frontend/src/types/search.ts`  
**Техническая шпаргалка:** [models.md](models.md)

---

## Зачем это нужно

Все scrapers приводят товары к **одному формату** `Product`. UI не знает, откуда товар — WB или Ozon — рисует одну и ту же карточку.

Pydantic на бэке и TypeScript на фронте описывают **одинаковые поля**.

---

## Product — один товар

| Поле | Что это | Важно |
|------|---------|-------|
| `title` | Название | |
| `price` | Цена | **В копейках!** 129990 = 1299.90 ₽ |
| `image_url` | Картинка | |
| `product_url` | Ссылка на сайт магазина | |
| `description` | Текст для раскрытия в UI | |
| `characteristics` | Словарь «Память» → «256 ГБ» | |
| `source` | `wildberries` / `ozon` / … | |
| `rating`, `reviews_count` | Если scraper достал | |

---

## SearchGroup — блок одного маркетплейса

```
«Ozon» — 5 товаров, min_price, список products
```

Дополнительно:

- **`error`** — текст, если scraper не смог (но приложение не упало).
- **`status`** — например `blocked_by_waf` у Ozon → особая плашка на фронте.

---

## SearchResponse — полный ответ поиска

Три части:

1. **`query`** — что искали, регион, сколько ms заняло.
2. **`summary`** — min / median / max цена **по всем** найденным товарам.
3. **`groups`** — массив SearchGroup (по одному на маркетплейс).

---

## SearchRequest — что шлёт фронт

```json
{ "query": "наушники", "region": "moscow" }
```

---

## Task models — для polling

- **`SearchTaskCreateResponse`** — только `task_id`.
- **`SearchTaskStatusResponse`** — status, message, groups (частично), result (когда готово).

---

## Частая ошибка новичка

Думать, что `price` в рублях. **Нет** — везде копейки (int). Фронт делит на 100 в `ProductCard.tsx`.

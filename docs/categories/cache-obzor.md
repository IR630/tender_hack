# Кэширование: обзор для нового человека

Где мы сохраняем результаты, чтобы не ходить на маркетплейсы повторно.

**Код:** `backend/app/core/cache.py`, `backend/cache_manager.py`, `ozon_public_scraper/storage/cache.py`  
**Техническая шпаргалка:** [cache.md](cache.md)

---

## В двух словах

Три **разных** кэша для разных задач. Это не одна база.

| Кэш | Для кого | Где лежит |
|-----|----------|-----------|
| Redis (sync) | Wildberries, Яндекс Маркет | сервер Redis |
| Diskcache | Ozon browser (опционально) | папка на диске |
| Redis (async) | Ozon public path | тот же Redis, другие ключи |

---

## 1. Redis для WB и YM

**Файл:** `app/core/cache.py`

- Ключ: `wb:search:moscow:наушники` или `ym:search:...`
- TTL: **6 часов** по умолчанию
- Если Redis упал — поиск **работает**, просто без кэша (warning в логах)

---

## 2. Diskcache для Ozon (браузер)

**Файл:** `cache_manager.py`

- По умолчанию **выключен** (`OZON_BROWSER_CACHE_ENABLED=false`)
- Ключ: нормализованный текст запроса
- Значение: JSON списка товаров после полного browser-пайплайна
- Hit → Chrome **не** запускается

Папка: `backend/data/ozon_disk_cache` (или из env).

---

## 3. Redis для Ozon public

**Файл:** `ozon_public_scraper/storage/cache.py`

Используется только если `OZON_USE_BROWSER=false`:

- кэш результатов SearXNG;
- кэш Open Graph по id товара;
- «заблокированные» URL.

---

## Зачем не один Redis на всё

- WB/YM — лёгкие ответы, часто меняются, общий TTL 6 ч.
- Ozon browser — тяжёлый результат (минуты работы Chrome), отдельный disk cache на демо часто off.
- Public Ozon — другой пайплайн, async-клиент.

---

## Настройки (.env)

```env
REDIS_URL=redis://localhost:6379/0
CACHE_TTL_SECONDS=21600
WB_CACHE_ENABLED=true
YM_CACHE_ENABLED=true
OZON_BROWSER_CACHE_ENABLED=false
```

---

## Docker

Volume `redis_data` — данные Redis.  
Volume `ozon_disk_cache` — disk cache Ozon в full stack compose.

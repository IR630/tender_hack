# Ozon scraper — идея и реализация

Как устроен парсер Ozon в `backend/app/scrapers/`: двухэтапный пайплайн,
nodriver и гибридный демо-стенд.

## Идея в одном абзаце

Ozon блокирует HTTP-скрапинг (curl_cffi, прокси, mobile API) через FAB/WAF.
Рабочий путь — **настоящий Chromium через nodriver** на хосте с `DISPLAY`.
Пайплайн: **broad search (до 36 товаров)** → **ML-фильтр (rubert-tiny2, top-5)** →
**enrich** (описание + характеристики с карточки) — всё в **одной сессии браузера**.

---

## Почему не curl_cffi

| Подход | Результат |
|--------|-----------|
| curl_cffi + chrome impersonate | 403 Antibot Captcha |
| Residential proxy (ASocks) | «Доступ ограничен / VPN» |
| business.ozon.ru / ozon.by / SW | 403 на все каналы |
| **nodriver + Chromium + DISPLAY=:0** | ✅ Поиск и карточки |

Подробнее о неудачных экспериментах — в истории коммитов ветки `feature/ozon`.

---

## Поток данных (two-stage)

```
query
  │
  ▼
run_browser_pipeline()  ← одна сессия Chromium
  │
  ├─ warmup ozon.ru (cookies, WAF)
  ├─ broad search URL → extract_broad_search_products()  (до 36 preview)
  ├─ filter_top_k_by_similarity()  (cointegrated/rubert-tiny2, top-5)
  └─ для каждого top-k (с паузой 5s):
        navigate product URL
        wait until data-widget / og:description загружены
        scroll → extract_product_enrichment()
        description = prose + «Характеристики: • …»
  │
  ▼
list[Product] → API → frontend
```

### Ключевые файлы

| Файл | Назначение |
|------|------------|
| `app/scrapers/ozon_browser.py` | nodriver, warmup, WAF, `run_browser_pipeline()` |
| `app/scrapers/two_stage_ozon.py` | broad → ML → enrich |
| `app/scrapers/ozon_seo_common.py` | парсинг HTML/JSON поиска и карточки |
| `app/scrapers/ozon_ml_filter.py` | cosine similarity, top-k |
| `app/scrapers/ozon.py` | маппинг в `Product` |

---

## Важные детали реализации

### 1. Одна сессия браузера

Раньше search + 5 enrich = 6 запусков Chromium → капча на карточках.
Сейчас весь пайплайн идёт в одном `run_browser_pipeline()`.

### 2. Warmup перед поиском

Перед первым search — заход на `https://www.ozon.ru/` для cookies и прохождения WAF.
Без warmup первый запрос часто давал ложный `blocked_by_waf`.

### 3. Ожидание SPA на карточке

Карточка товара отдаёт «пустой» HTML (~340 KB), через 3–5 с JS подгружает
полную страницу (~1 MB с `og:description` и `data-widget`).

`_is_product_detail_ready()` ждёт `og:description` или ≥20 виджетов, затем scroll.

### 4. Описание в UI

`description` = текст описания + блок «Характеристики: • ключ: значение».
Словарь `characteristics` сохраняется отдельно.

---

## Конфиг (.env)

```env
OZON_USE_BROWSER=true
OZON_TWO_STAGE_ENABLED=true
OZON_BROAD_SEARCH_MAX=36
OZON_ML_TOP_K=5
OZON_ENRICH_ENABLED=true
OZON_ENRICH_DELAY_SECONDS=5
OZON_ENRICH_WAIT_SECONDS=15
OZON_BROWSER_WARMUP_HOME=true
OZON_BROWSER_MAX_RETRIES=1
OZON_BROWSER_TOTAL_TIMEOUT_SECONDS=45
OZON_PIPELINE_TIMEOUT_SECONDS=180
OZON_BROWSER_CACHE_ENABLED=false
```

---

## Гибридный демо-стенд

Ozon **не работает в Docker** (Xvfb → WAF). Демо: frontend + infra в Docker,
API на хосте с реальным дисплеем.

```bash
./start_demo.sh
```

- UI: http://127.0.0.1:5173
- API: http://127.0.0.1:8000

Подробнее: [ozon-hybrid-demo.md](ozon-hybrid-demo.md)

---

## Fail-fast и статусы

- WAF / timeout → `status: "blocked_by_waf"` в `SearchGroup`, плашка на фронте
- Пустой search после retry → ошибка «товары не найдены»
- Enrich без данных → товар возвращается с preview (title, price, url, image)

---

## Удалённый сервер (будущее)

Да, парсер можно вынести на отдельный хост: нужны Chromium, `DISPLAY` или Xvfb,
исходящий доступ к ozon.ru. API вызывает scraper как микросервис или по SSH-туннелю.

---

## Отладка

```bash
cd backend
DISPLAY=:0 uv run python scripts/debug_ozon.py "принтер hp"
uv run pytest tests/test_ozon_seo_common.py tests/test_two_stage_ozon.py -q
```

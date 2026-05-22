# Wildberries scraper — findings & current state (2026-05-23)

Краткая выжимка живого разбора WB API. **TL;DR:** структура скрапера готова и
покрыта тестами, но против боевого API WB она сейчас возвращает **0 товаров** —
WB закрутил анти-бот за последние сутки. Ниже что именно мешает и куда копать.

## Текущее состояние кода

- `backend/app/scrapers/wb.py` — реализация на `httpx`: поиск через
  `search.wb.ru/.../v4/search`, резолв basket-CDN под картинки/характеристики,
  обогащение top-K через `card.json`. Логика верная, юнит-тесты зелёные
  (`backend/tests/test_wb_scraper.py`, сеть замокана).
- **Против живого API возвращает 0** из-за трёх анти-бот гейтов (ниже). Это WIP.
- **Диагностика добавлена** (2026-05-23): `wb.py`, `orchestrator/search.py`,
  `main.py` теперь логируют, на каком шаге и почему WB отдаёт 0 — HTTP-ошибка /
  блок WAF (429) / не-JSON / PoW / воронка `raw → usable → returned`. Логирование
  включается в `main.py` (`logging.basicConfig`, уровень из `settings.debug`).

## TODO (для следующего исполнителя)

**Задача: мигрировать `wb.py` с `httpx` на `curl_cffi(impersonate="chrome")`.**

Единственная причина 0 товаров сейчас — гейт №1 (TLS-фингерпринт): на живом API
`httpx` всегда `429`, а `curl_cffi` impersonate=chrome → `200` + 100 товаров (PoW
решать НЕ нужно, см. гейт №2). Готовый образец миграции — `yandex_market.py`, он уже
на `curl_cffi`.

- [ ] Заменить `httpx.AsyncClient` в `wb.py` на `curl_cffi`. Скрапер полностью
      асинхронный (`asyncio.gather`, семафоры) → брать `curl_cffi.requests.AsyncSession`
      ЛИБО обернуть синхронный `curl_cffi.requests` в пул потоков, как в yandex.
- [ ] Передавать `impersonate="chrome"` на ВСЕХ запросах (search, HEAD basket-проб,
      `card.json`) — иначе CDN-пробы тоже могут ловить блок.
- [ ] Сохранить browser-заголовки (`Origin`/`Referer` wildberries.ru, `Accept-Language` ru-RU).
- [ ] Переписать `backend/tests/test_wb_scraper.py`: сейчас мокают `httpx.MockTransport`
      → адаптировать под мок/транспорт `curl_cffi`.
- [ ] Прогнать против живого API с чистого РФ-IP (гейт №3): throttle + кэш `vol→host`.
- [ ] После миграции проверить по логам, что воронка показывает `raw → usable → returned`
      (диагностика уже на месте, отдельно её делать не нужно).

Не входит: решение PoW (сейчас не требуется), Playwright-фоллбэк.

## Три анти-бот гейта WB (подтверждены на живом API 2026-05-23)

1. **TLS-фингерпринт.** Запрос обычным `httpx`/`curl` → `HTTP 429` при любых
   заголовках: WAF WB (`wbaas`/DDoS-Guard) режет небраузерный JA3/JA4 TLS.
   **`curl_cffi` с `impersonate="chrome"` → `HTTP 200`.** Текущий `wb.py` на
   `httpx`, поэтому и упирается в 429. → миграция на `curl_cffi` (уже в зависимостях).

2. **Proof-of-Work на v4 — challenge есть, но СЕЙЧАС не блокирует.** v4 по-прежнему
   шлёт заголовок `X-Pow: status=invalid;challenge=...`. **Повторная проверка
   2026-05-23 (в рамках задачи по диагностике): `curl_cffi` impersonate=chrome →
   `HTTP 200` и `products` len=100 ДАЖЕ при `X-Pow: status=invalid`.** То есть
   сейчас v4 отдаёт полные результаты без решения PoW — раннее сегодняшнее «v4
   отдаёт `[]`» было ошибочным либо гейт включается периодически. **Вывод: решать
   PoW сейчас НЕ нужно — достаточно миграции `httpx`→`curl_cffi`.** Механика PoW
   (ниже) остаётся фоллбэком на случай, если WB снова включит блокировку. Решённый
   токен тогда возвращается в заголовке запроса `X-Pow`.

3. **IP / rate-limit.** Иностранный/датацентровый/VPN IP блокируется жёстко
   (главная `wildberries.ru` → `498`, поиск → `429`) независимо от TLS. Нужен
   **чистый российский IP**. Локально это всплыло из-за VPN с зарубежным выходом
   (full-tunnel) — лечится сплит-туннелем для диапазонов WB. На РФ-сервере в
   проде вопрос отпадёт. Диапазоны WB: `185.62.202.0/24`, `185.138.252.0/22`,
   `213.184.155.0/24`, `213.184.156.0/24`, `85.198.79.0/24`.

## Механика PoW (реверс из web-бандла)

Бандл WB: `static-basket-01.wbbasket.ru/vol2/site/app/*.js`. Это **scrypt-hashcash,
посчитанный в WebAssembly**:

1. Сервер: `X-Pow: status=invalid;challenge=<n>,<r>,<p>,<target-hex>,<seed-uuid>,<session_id-uuid>,<exp-ts>,<service>,<payload-b64>,<signature-hex>`.
2. `entry.js` → `tokenService` парсит, создаёт `Hashcash(params, created=now-sec, deviceId=sessionId, counter=1, limit=1000)` (чанк `48817...js`).
3. → Web Worker `/w/index.worker.js` (=`pow.worker.js`, за антиботом/498, тянется через браузерную сессию) → грузит `*.module.wasm`.
4. WASM крутит `counter`, пока scrypt-хэш ≤ `target`, и возвращает токен-строку.
5. Токен кэшируется в localStorage как `session-pow-token` (лимит неудач 5), ставится в заголовок `X-Pow` → сервер отдаёт товары.

Домашний антибот (`498` на главной) — **отдельный** механизм:
`challenge_solver_v1.0.4.js` → кука `x_wbaas_token`. Для search API он **не нужен**
(`search.wb.ru` отдаёт `200`+challenge без этой куки).

## Открытая развилка (как проходить PoW)

| Путь | Суть | Сложность |
|------|------|-----------|
| **WASM WB через `wasmtime`** | скачать `.module.wasm`, дёргать его экспорт из Python | средняя; устойчиво к смене params |
| **Playwright** | браузер решает PoW сам, перехватываем search-XHR | средне-высокая: headless детектится + Chromium в Docker |
| Чистый Python | реимплементировать scrypt+target+формат | высокая (реверс WASM), хрупко |

Гейты №1 (`curl_cffi`) и №3 (throttle + кэш + чистый IP) нужны при **любом** выборе.

## Связанное

- **Яндекс Маркет**: основной путь (`curl_cffi`) ловит `403`, Playwright-фоллбэк
  падает — **в Docker-образе нет Chromium** (`Dockerfile.api` не делает
  `playwright install`). Тот же Chromium-в-Docker понадобится, если для WB
  выберем Playwright.

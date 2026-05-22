# Architecture Constraints (Hackathon Rules)

Эти ограничения обязательны для соответствия условиям Tender Hack.

## Разрешено

- Self-hosted сервисы в Docker на серверах команды:
  - SearXNG (метапоиск)
  - Ollama (локальная LLM)
  - Moondream2 / rubert-tiny2 (локальный инференс)
  - Redis (кеш)
- Парсинг маркетплейсов через HTTP/Playwright без официальных API
- Открытые ML-модели с локальным инференсом

## Запрещено

- Внешние API поисковых систем (Яндекс.Поиск, Google Search, Bing API)
- Внешние API LLM (OpenAI, Gemini, Claude, OpenRouter и т.п.)
- Low-code / No-code платформы
- Зависимость от сторонней инфраструктуры в runtime:
  - Cloudflare Workers как прокси
  - SaaS-сервисы, не развёрнутые командой

## Практические решения

| Задача | Решение |
|---|---|
| 4-й источник | SearXNG self-hosted в Docker |
| Синонимы / сложные запросы | Ollama локально + кеш |
| Vision для произвольных сайтов | Moondream2 локально |
| Обход блокировок | curl_cffi, Playwright stealth, ротация User-Agent, кеш |
| Прокси | Собственный VPS (если есть), не Cloudflare Workers |

## Четвёртый источник

- Не может быть фиксированным сайтом или ещё одним маркетплейсом
- Должен быть динамическим: разные домены на разные запросы
- SearXNG self-hosted — допустимо: это ваш сервер, не «API Google»

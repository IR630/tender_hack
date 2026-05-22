# Git Flow — Tender Hack

Модель разработки для команды из 4 человек на хакатоне.

## Модель: Trunk-based

```
main (защищена)
  ↑
  PR ← feature/scrapers-wb
  PR ← feature/frontend-search-ui
  PR ← feature/query-symspell
```

`main` — единственная постоянная ветка. Она всегда должна быть в рабочем состоянии и готова к демо.

## Правила

1. **Прямой push в `main` запрещён.** Все изменения — только через Pull Request.
2. **PR мёржится только если:**
   - CI прошёл (все checks green)
   - есть минимум **1 approve** от другого участника команды
   - ветка актуальна относительно `main`
3. **Именование веток:** `feature/<module>-<short-desc>`
   - `feature/scrapers-wb`
   - `feature/scrapers-ozon-stealth`
   - `feature/sources-searxng`
   - `feature/frontend-search-ui`
   - `feature/query-symspell`
4. **Коммиты (рекомендуется):** Conventional Commits
   - `feat(scrapers): add WB parser`
   - `fix(api): handle empty search query`
   - `chore(ci): add docker build job`
5. **Перед открытием PR локально:**
   ```bash
   # Backend
   cd backend && uv sync && uv run ruff check . && uv run pytest

   # Frontend
   cd frontend && pnpm install && pnpm lint && pnpm build

   # Docker (опционально)
   docker compose -f docker/docker-compose.yml build
   ```

## Владение модулями

| Участник | Папка | Зона ответственности |
|---|---|---|
| Dev 1 | `frontend/` | React UI, поиск, карточки товаров |
| Dev 2 | `backend/app/scrapers/` | WB, Ozon, Яндекс Маркет |
| Dev 3 | `backend/app/sources/` | 4-й источник, SearXNG, anti-bot |
| Dev 4 | `backend/app/api/`, `query/`, `ml/`, `orchestrator/`, `core/` | API, оркестратор, ML |

Кросс-модульные изменения (например, `Product` model) — согласовать в чате и запросить ревью у Dev 4.

## Настройка Branch Protection (GitHub)

Владелец репозитория настраивает один раз:

1. GitHub → **Settings** → **Branches** → **Add branch protection rule**
2. Branch name pattern: `main`
3. Включить:
   - **Require a pull request before merging** (1 approval)
   - **Require status checks to pass before merging**
     - `backend`
     - `frontend`
     - `docker-build`
   - **Require branches to be up to date before merging**
   - **Do not allow bypassing the above settings** (включая admins)

## CODEOWNERS

Файл [`.github/CODEOWNERS`](../.github/CODEOWNERS) автоматически назначает ревьюеров по изменённым путям. Замените `@devN-github` на реальные GitHub-логины команды.

## Типичный workflow

```bash
git checkout main
git pull origin main
git checkout -b feature/scrapers-wb

# ... работа ...

git add backend/app/scrapers/wb.py
git commit -m "feat(scrapers): implement WB search stub"
git push -u origin feature/scrapers-wb

# Открыть PR на GitHub → дождаться CI + approve → Merge
```

## Что делать при конфликтах

1. `git checkout feature/your-branch`
2. `git fetch origin && git rebase origin/main`
3. Разрешить конфликты, `git rebase --continue`
4. `git push --force-with-lease`

Rebase предпочтительнее merge-коммитов — история `main` остаётся линейной.

## Hotfix на демо

Если на защите что-то сломалось:

```bash
git checkout -b feature/hotfix-demo-search main
# минимальный фикс
# PR → быстрый review → merge
```

Не коммитить напрямую в `main`, даже под давлением дедлайна.

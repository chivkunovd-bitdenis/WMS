# AGENTS

This repo is optimized for an “autopilot” development loop.

## Product decisions (source of truth)

Before picking an issue, read **[docs/MVP_DECISIONS_RU.md](docs/MVP_DECISIONS_RU.md)** (RU): tenants, billing liter‑day, WB import‑only, portal scope, printer 58×40, **RU product terms for FF↔MP flows** (поставка vs отгрузка — см. раздел «Терминология» там же).

Epic map for splitting work: **[docs/BACKLOG_EPICS_RU.md](docs/BACKLOG_EPICS_RU.md)**.

## Autopilot loop (single feature at a time)

1. Pick the next GitHub Issue with label `ready` (skip `blocked`).
2. Re-state the acceptance criteria (Given/When/Then) and identify impacted modules. **Same step — test coverage traceability (mandatory):** produce the artifact described in **[Test coverage traceability](#test-coverage-traceability-mandatory-before-vertical-slice)** below (issue + copy into PR for CI). **Никакого обязательного порядка вызова Cursor-агентов:** единственный жёсткий контракт — **зелёный CI** и правила ниже.
3. Implement **vertical slice**:
   - API routes only in `backend/app/api` (в т.ч. интеграции: `wildberries_integration.py` → `/integrations/wildberries/...`, в т.ч. `status`, `sellers/{id}/tokens`, `sellers/{id}/imported-cards`, `sellers/{id}/imported-supplies`, `sellers/{id}/link-product` для админа)
   - business logic only in `backend/app/services`
   - data models only in `backend/app/models`
   - DB access only via `backend/app/db`
   - Celery tasks only in `backend/app/tasks` (enqueue from API; broker via `CELERY_BROKER_URL`; unset `CELERY_BROKER_URL` uses FastAPI `BackgroundTasks` for local/tests; типы джоб: `movements_digest`, `wildberries_cards_sync`, `wildberries_supplies_sync` + `seller_id` в теле)
   - Playwright webServer для API: в `frontend/playwright.config.ts` задаётся `E2E_MOCK_WB_CARDS=1` и `E2E_MOCK_WB_SUPPLIES=1` — заглушки в `fetch_cards_list` / `fetch_supplies_list` (без сети наружу).
4. Add tests:
   - backend: pytest for core logic/validation
   - frontend: Playwright e2e that verifies **user-visible outcome** (not just HTTP 200). Each new or materially changed scenario must **map to a row** in the issue’s `### Test coverage` block (existing `TC-Sxx-yyy` or `TC-NEW-*` from step 2); reference the TC id in a **comment** above the `test()` or in the test title so traceability survives refactors.
5. Run gates locally:
   - backend: `ruff check . && mypy . && pytest` (in `backend/`)
   - frontend: `npm run build && npm run test:e2e` (in `frontend/`)
6. Open PR with the template and wait for CI green.
7. Only after green CI: mark issue done and move to next `ready`.

## Test coverage traceability (mandatory before vertical slice)

Canonical manual / future-automation catalog: **[docs/IMPLEMENTED_PRODUCT_SCENARIOS_TEST_CASES_EN.md](docs/IMPLEMENTED_PRODUCT_SCENARIOS_TEST_CASES_EN.md)** (IDs `TC-Sxx-yyy`). Scenario context: **[docs/IMPLEMENTED_PRODUCT_SCENARIOS_EN.md](docs/IMPLEMENTED_PRODUCT_SCENARIOS_EN.md)**. Conflicts with scope → **[docs/MVP_DECISIONS_RU.md](docs/MVP_DECISIONS_RU.md)**.

**Кто заполняет:** любой автор работы (человек или агент) **до** merge; важно не роль, а то, что в PR есть проверяемый блок (см. **CI enforcement** — GitHub сам отклонит красным job, без вашего «слежения» за субагентами).

**Artifact — add to the GitHub Issue** (description or first comment), section heading exactly:

```markdown
### Test coverage

| TC-ID | Title (short) | Applies (Y/N) | Notes |
|-------|-----------------|---------------|-------|
| TC-S06-001 | … | Y | |
| TC-NEW-001 | (draft) … | Y | Given/When/Then + negative cases if any |
```

- **Y:** this issue implements or regression-touches that case; link to subsection in the EN test-case doc when an ID already exists.
- **Gaps:** behaviour not yet in the doc → add rows with **`TC-NEW-00n`** and full Given/When/Then + restrictions. Playwright must only target **Y** rows (existing or NEW).
- **Doc PR rule:** if the issue introduces **new** user-visible rules (new `TC-NEW-*` that should live permanently), extend **`docs/IMPLEMENTED_PRODUCT_SCENARIOS_TEST_CASES_EN.md`** (and RU if maintained) **in the same PR** as the feature, assigning final `TC-Sxx-yyy` IDs or keeping `TC-NEW` until someone renumbers — but the file must not drift from the issue table.

### Quality bar (не «галочка ради CI»)

Цель — чтобы строки **Notes** были **проверяемым мини-спеком**, а не пустышкой.

- Для каждой строки с **Applies = Y** в **Notes**: что делает пользователь, **что видно** при успехе, **негатив или ограничение** (если уместно), границы роли/статуса если важно. Стиль как в `IMPLEMENTED_PRODUCT_SCENARIOS_TEST_CASES_EN.md` (шаги + Expected + Negative).
- Минимум **две** строки таблицы с `TC-...` и хотя бы одна **Y**.
- В тексте секции должны встречаться **смысловые маркеры** (Given/When/Then или дано/когда/тогда, negative/негатив, restriction/огранич…, expected/ожидаемо) — **CI считает их количество** (`scripts/ci/check_pr_test_coverage.py`), чтобы отсечь однострочный формализм.
- Если фича **тривиальная** и полный блок избыточен — только тогда label **`skip-test-coverage-check`** на PR (не злоупотреблять).

**Опционально для Cursor:** [`.cursor/skills/feature-test-coverage/SKILL.md`](.cursor/skills/feature-test-coverage/SKILL.md) — подсказка агенту, как оформить таблицу; **не часть пайплайна GitHub**.

## CI enforcement (GitHub Actions) — жёсткий контракт без «конвейера агентов»

На **pull_request**, если дифф затрагивает `frontend/src`, `frontend/tests-e2e`, `backend/app/api` или `backend/app/services`:

- **Обязателен** осмысленный блок `### Test coverage` в **описании PR** (не короткая заглушка): минимальная длина, ≥2 строки с `TC-`, строка с **Y**, несколько **маркеров Given/When/Then или негативов/ограничений** в секции — скрипт `scripts/ci/check_pr_test_coverage.py` (см. **Quality bar** выше). **Включите branch protection:** merge в `main` только при зелёном CI.
- Если менялись только файлы в `frontend/tests-e2e/**`, каждый затронутый `*.spec.ts` должен содержать упоминание **`TC-Sxx-yyy`** или **`TC-NEW-*`** (скрипт `scripts/ci/check_e2e_tc_mentions.py`).
- **Обход:** label на PR **`skip-test-coverage-check`** — только осознанно (доки, мелкий chore после согласования).

**Визуальная целостность shell:** см. Playwright `frontend/tests-e2e/admin-shell-layout.spec.ts` (навигация/единый `app-root`); при необходимости расширяйте аналогичными проверками ключевых `data-testid`. Скриншотные тесты (`toHaveScreenshot`) — опционально, если понадобится пиксельный контроль.

## Уже написанный код (валидация, не «с нуля»)

Автогeneration без жёстких ворот дала объём кода, который **не совпадает** с ожидаемым UX (пример: после логина «второй шаг» ломается). **Переписывать всё с нуля не обязательно** — нужно **подтвердить и закрепить** поведение правилами репозитория.

**Что делать по шагам:**

1. **Получить срез с `main`:** локально `backend/` → `ruff check . && mypy . && pytest`; `frontend/` → `npm run build && npm run test:e2e`. Это первая объективная картина: зелёный CI на main или список красных тестов/сборки.
2. **P0-цепочка пользователя:** одна issue (например «Стабилизация: логин → экран после логина») с таблицей `### Test coverage` по релевантным `TC-S02-*`, `TC-S15-*` и т.д. — в **Notes** явно: что сейчас сломано, что должно быть видно после фикса.
3. **Правки только через PR** с полным блоком Test coverage в описании PR (как требует CI) + новые/усиленные Playwright-сценарии на этот путь. Так **старый код валидируется и фиксируется** тестами, а не остаётся «как получилось».
4. **Документы:** если фактическое поведение после правок расходится с `IMPLEMENTED_PRODUCT_SCENARIOS_*` — в том же или следующем PR обновить сценарии/кейсы, чтобы снова не уехать в автопилот без источника правды.

Новые правила **не магически исправляют** уже влитый в `main` код: они **заставляют каждое следующее изменение** (включая починку) пройти через осмысленное покрытие и CI. Долг по качеству закрывается **серией стабилизационных PR**, пока критический путь и e2e не станут зелёными.

## E2E rule (must be user-centric)

Every feature that changes UI flow must ship with at least one Playwright scenario that:
- performs actions through the UI
- asserts visible UI state and primary outcomes
- uses stable selectors (`data-testid`)

The scenario must match the real user path (e.g. register → screen that uses the new API), not an isolated HTTP check. With the default Playwright web server (one API + sqlite file), CI runs **`workers: 1`** to avoid DB lock flakes. In React async submit handlers, capture `const form = e.currentTarget` **before** any `await`, then call `form.reset()` — otherwise Strict Mode can leave `currentTarget` null after awaits.

When asserting on network: subscribe with `page.waitForResponse` **in parallel** with the UI action (`Promise.all([waitForPostOk(...), locator.click()])`). If you `click()` first and only then await the response, the request may already have finished and the test will time out. After a successful submit that resets the form, the next step must refill **all** required fields (e.g. product dimensions), not only the fields that differ from defaults.


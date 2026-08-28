# AGENTS

## ⛔️ ЕДИНСТВЕННЫЙ ПРАВИЛЬНЫЙ ПУТЬ ПРОЕКТА — ЧИТАТЬ ПЕРВЫМ

```
/Users/deniscivkunov/Projects/WMS
```

Это единственная рабочая копия WMS. Перед первой правкой проверь `pwd`. Если ты не здесь — **остановись и скажи пользователю**, ничего не правь.

- **Не создавай вторую копию проекта.** Никаких клонов на Рабочем столе, в `/tmp`, никаких папок `WMS-<что-то>`, `WMS 2`, `WMS copy`. Нужна изоляция — `git worktree` внутри `.worktrees/`, с уборкой за собой.
- **Проект не должен лежать на Рабочем столе:** он синхронизируется с iCloud, из-за чего `git status` виснет минутами, а файлы (был случай с `frontend/package.json`) физически пропадают с диска, оставаясь в гите.
- **Актуальная ветка — `etalon`.** Эталон фронта: таблица FBS-заказов из четырёх колонок — `Товар`, `Селлер`, `Маршрут сдачи`, `Отгрузить до` (+ `Статус` вне вкладки «Новые»). Шесть колонок с `Товар и заказ` / `Остаток` — это регресс со старых веток.
- **Задача про бэк — фронт не трогаем.** Никаких «заодно» добавленных колонок, чипов, статусов и технических подсказок. Правки фронта — только по явному запросу и строго по макету.

Подробности и история вопроса — в [CLAUDE.md](CLAUDE.md).

---

This repo is optimized for an “autopilot” development loop.

## Product decisions (source of truth)

Before picking an issue, read **[docs/MVP_DECISIONS_RU.md](docs/MVP_DECISIONS_RU.md)** (RU): tenants, billing liter‑day, WB import‑only, portal scope, printer 58×40, **RU product terms for FF↔MP flows** (поставка vs отгрузка — см. раздел «Терминология» там же).

Epic map for splitting work: **[docs/BACKLOG_EPICS_RU.md](docs/BACKLOG_EPICS_RU.md)**.

## UI (портал FF)

Новые и правимые экраны фулфилмента — **единый MUI-дизайн** (без legacy `Card`/`Input` из `frontend/src/ui` в основной области). Эталон: `FfProductsCatalogScreen.tsx`. Правила: **[docs/UI_DESIGN_SYSTEM_RU.md](docs/UI_DESIGN_SYSTEM_RU.md)**.

## Как ведётся задача

Ролей, вердиктов и изолированных агентов-приёмщиков в этом репозитории нет.
Одна голова ведёт задачу от постановки до сдачи и отвечает за результат целиком.

1. Взять задачу: текст владельца или GitHub Issue с меткой `ready` (пропуская
   `blocked`).
2. Сформулировать, что считается сделанным, и понять, какие модули задеты.
   Тем же шагом — таблица покрытия из раздела
   **[Test coverage traceability](#test-coverage-traceability-mandatory-before-vertical-slice)**:
   она нужна CI и служит проверяемым мини-спеком, а не формальностью.
3. Реализовать **вертикальный срез** с соблюдением слоёв:
   - роуты только в `backend/app/api` (интеграции: `wildberries_integration.py`
     → `/integrations/wildberries/...`, в т.ч. `status`, `sellers/{id}/tokens`,
     `sellers/{id}/imported-cards`, `sellers/{id}/imported-supplies`,
     `sellers/{id}/link-product` для админа)
   - бизнес-логика только в `backend/app/services`
   - модели только в `backend/app/models`
   - доступ к БД только через `backend/app/db`
   - фоновые задачи только в `backend/app/tasks` (ставятся из API; брокер через
     `CELERY_BROKER_URL`; без него используется FastAPI `BackgroundTasks`;
     типы джоб: `movements_digest`, `wildberries_cards_sync`,
     `wildberries_supplies_sync` + `seller_id` в теле)
   - Playwright webServer для API: в `frontend/playwright.config.ts` заданы
     `E2E_MOCK_WB_CARDS=1` и `E2E_MOCK_WB_SUPPLIES=1` — заглушки в
     `fetch_cards_list` / `fetch_supplies_list`, без сети наружу.
4. Написать тесты: бэк — pytest на логику и проверки; фронт — Playwright на
   **видимый пользователю результат**, а не на код ответа 200. Каждый новый или
   существенно изменённый сценарий ссылается на строку `TC-` в комментарии над
   `test()` или в его названии, чтобы связь пережила рефакторинг.
5. Прогнать ворота локально:
   - бэк: `ruff check . && mypy . && pytest` (в `backend/`)
   - фронт: `npm run build && npm run test:e2e` (в `frontend/`)
6. Посмотреть результат **своими глазами в живом браузере**, если менялся экран.
   Чтение кода, curl и зелёный Playwright этого не заменяют — они не показывают
   разорванную строку, съехавшую колонку и направляющую в пустоту.
7. Открыть PR по шаблону, дождаться зелёного CI, влить.

**Про тесты по ходу работы.** Полный набор — это тысяча с лишним тестов и
пятнадцать минут. Гонять его после каждой правки бессмысленно: по ходу запускать
точечно затронутые файлы, полный прогон — один раз перед сдачей. Упало — чинить
и перезапускать упавшее по имени, а не весь набор заново.

## Test coverage traceability (mandatory before vertical slice)

Canonical manual / future-automation catalog: **[docs/IMPLEMENTED_PRODUCT_SCENARIOS_TEST_CASES_EN.md](docs/IMPLEMENTED_PRODUCT_SCENARIOS_TEST_CASES_EN.md)** (IDs `TC-Sxx-yyy`). Scenario context: **[docs/IMPLEMENTED_PRODUCT_SCENARIOS_EN.md](docs/IMPLEMENTED_PRODUCT_SCENARIOS_EN.md)**. Conflicts with scope → **[docs/MVP_DECISIONS_RU.md](docs/MVP_DECISIONS_RU.md)**.

**Кто заполняет:** автор работы **до** merge. Смысл не в галочке для CI, а в
том, чтобы в PR лежал проверяемый мини-спек: что делает пользователь и что он
должен увидеть.

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
- Метка `skip-test-coverage-check` снимает эту проверку. Ставить после явного
  согласования с владельцем.

## CI enforcement (GitHub Actions)

На **pull_request**, если дифф затрагивает `frontend/src`, `frontend/tests-e2e`, `backend/app/api` или `backend/app/services`:

- **Обязателен** осмысленный блок `### Test coverage` в **описании PR** (не короткая заглушка): минимальная длина, ≥2 строки с `TC-`, строка с **Y**, несколько **маркеров Given/When/Then или негативов/ограничений** в секции — скрипт `scripts/ci/check_pr_test_coverage.py` (см. **Quality bar** выше). **Включите branch protection:** merge в `main` только при зелёном CI.
- Если менялись только файлы в `frontend/tests-e2e/**`, каждый затронутый `*.spec.ts` должен содержать упоминание **`TC-Sxx-yyy`** или **`TC-NEW-*`** (скрипт `scripts/ci/check_e2e_tc_mentions.py`).
- Метка **`skip-test-coverage-check`** снимает проверку таблицы — после явного
  согласования с владельцем.

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

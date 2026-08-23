# Фича 1

# DEV · Read-only API коробов и грузомест для каталога

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/app/services/inbound_package_catalog_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/app/api/inbound_package_catalog.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/app/main.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend/tests/test_inbound_package_catalog.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md`

Реализованы `GET /operations/inbound-packages` и
`GET /operations/inbound-packages/lookup?barcode=...`. Оба используют
`require_catalog_cells_read_access`; сервис читает данные текущего тенанта,
считает только `max(quantity - posted_qty, 0)` и не вызывает изменяющее
`open_box_by_barcode`.

## Миграции

Нет: переиспользованы существующие таблицы приёмки только для чтения.

## Тесты

- `backend/tests/test_inbound_package_catalog.py` — состав обычного списка,
  положительный остаток, новый пустой короб, исключение полностью разложенного
  короба, незавершённое грузоместо и стабильный порядок.
- Точный поиск завершённого короба и грузоместа, одинаковый `404` для
  неизвестного и чужого штрихкода, тенантная граница и отсутствие побочных
  изменений `intake_opened_at`, `intake_closed_at`, количеств и статуса.
- Доступ администратора, сотрудников с `cells`/`inventory` и отказ сотруднику
  только с правом приёмки.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend && ruff check app/services/inbound_package_catalog_service.py app/api/inbound_package_catalog.py app/main.py tests/test_inbound_package_catalog.py` — пройдено: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend && mypy app/services/inbound_package_catalog_service.py app/api/inbound_package_catalog.py app/main.py` — в изменённых модулях ошибок нет; команда завершается с 6 существующими ошибками в импортируемых, не затронутых сервисах: `inventory_movement_report_service.py`, `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`, `wildberries_product_import_service.py`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/backend && pytest -q tests/test_inbound_package_catalog.py` — пройдено: `2 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && python3 scripts/ci/back_guard.py` — не выполнен: в рабочей копии отсутствует `scripts/ci/back_guard.py`; поиск по репозиторию также не нашёл этот файл.
- `check_migrations.py` не применим: миграций нет; файла скрипта в этой рабочей копии также нет.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались. Боевой сервер не использовался.

## Не реализовано

Нет. Реализован только атом 1 из `FEATURES.md`; UI и e2e-атомы не затрагивались.

# Фича 2

# DEV · Раскрываемый блок коробов и грузомест в каталоге

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/src/screens/v2/FfCatalogInboundPackages.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/src/screens/v2/FfProductsCatalogScreen.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md`

Реализован только атом 2 из `FEATURES.md`: под таблицей каталога появился свёрнутый
раздел с ленивым read-only списком, адресным поиском через существующее поле и
состояниями состава, пустоты и ошибки. Адресный результат и ошибка ленивого списка
держатся независимо; повторный скан не позволяет позднему ответу открыть старый объект.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup && python3 scripts/ui/ui_guard.py` — зелёный, новых нарушений нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npx vitest run --passWithNoTests src/screens/v2/FfCatalogInboundPackages.tsx src/screens/v2/FfProductsCatalogScreen.tsx` — зелёный. В этом атоме нет выделенного unit-файла S-16; команда ограничена двумя затронутыми экранами и завершилась без найденных тестов.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npm run test:unit -- --passWithNoTests src/screens/v2/FfCatalogInboundPackages.tsx src/screens/v2/FfProductsCatalogScreen.tsx` — красный до запуска тестов: `sh: vitest: command not found`. Локальная зависимость `vitest` в этой рабочей копии недоступна из npm-скрипта; код и проверка через `npx vitest` выше не выявили ошибок.

Полные `pytest`, `ruff check .`, `mypy .` и общий frontend-регресс не запускались по
прямому ограничению атомарной проверки.

## Не реализовано

Нет. Реализован ровно атом 2. Новый e2e-сценарий и постоянная трассировка TC-ID относятся
к следующему атому 3 и не затрагивались.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались. Боевой сервер
`194.87.96.144` не использовался.

# Фича 3

# DEV · Пользовательский e2e-сценарий и постоянная трассировка правил

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend/tests-e2e/catalog-box-lookup.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/docs/IMPLEMENTED_PRODUCT_SCENARIOS_TEST_CASES_EN.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/night/catalog-box-lookup-20260823/cards/01-catalog-box-lookup/DEV.md`

Реализован только атом 3 из `FEATURES.md`. Новый Playwright-сценарий проходит через
`S-17` (приёмка: создание короба и грузоместа, наполнение), `S-16` (скан и видимый
состав) и `S-20` (частичная и полная раскладка). Он также проверяет безопасный единый
текст для неизвестного и чужого кода, состояние грузоместа без состава и доступ
сотрудника с правом `cells`. Постоянные правила внесены под `TC-NEW-CATALOG-PACKAGES-001`
— `TC-NEW-CATALOG-PACKAGES-004`; тест ссылается на них комментарием.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && python3 ../scripts/ui/ui_guard.py` — зелёный, новых нарушений нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npm run test:unit -- --passWithNoTests tests-e2e/catalog-box-lookup.spec.ts` — зелёный.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/catalog-box-lookup-20260823/lane-1-01-catalog-box-lookup/frontend && npx playwright test tests-e2e/catalog-box-lookup.spec.ts` — зелёный.

Полный backend `pytest`, `ruff check .`, `mypy .` и общий e2e-регресс не запускались:
они прямо запрещены для атомарной проверки этого шага.

## Git

Commit не создан: `git add` не получил права создать
`/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-catalog-box-lookup/index.lock`
(`Operation not permitted`). Изменения остаются локальными в этой рабочей копии и требуют
фиксации из окружения с доступом к служебной директории Git.

## Не реализовано

Нет. Реализован ровно атом 3; код экранов и API не менялся.

## Находки

Секреты, ключи, токены, `.env` и кабинеты учётных данных не открывались. Боевой сервер
`194.87.96.144` не использовался.

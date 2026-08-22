# Фича 1

# Backend development · 07-reporting · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py` — backfill сохраняет доступные текущие измерения, но помечает каждую исторически реконструированную строку как `reporting_dimensions_legacy`, чтобы текущая связь не была выдана за доказанный факт прошлого.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_movement_reporting_dimensions.py` — зафиксирован консервативный контракт legacy-backfill и индексов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/models/inventory_movement.py alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py tests/test_inventory_movement_reporting_dimensions.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy app/models/inventory_movement.py` — `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_inventory_movement_reporting_dimensions.py` — `2 passed in 0.02s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ci/back_guard.py` — не применён: файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ci/check_migrations.py` — не запускался, потому что названный скрипт также отсутствует в этой рабочей копии.
- `git diff --check` — без ошибок.

## Не реализовано

- Пункты следующих атомов из `FEATURES.md` не затрагивались.
- Фактический PostgreSQL round-trip миграции не запускался: в репозитории нет требуемых CI-скриптов, а отдельный тестовый URL базы не предоставлен. Целевой тест фиксирует SQL-контракт миграции.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/inventory_service.py` — общий writer уже записывает `seller_id=Product.seller_id` и `warehouse_id=StorageLocation.warehouse_id` при создании `InventoryMovement` в той же транзакции, что и изменение остатка.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_service_reporting_dimensions.py` — сценарий движения с последующей перепривязкой товара и ячейки подтверждает сохранение исходных измерений.

## Гейты

- `ruff check .` — FAIL: 82 существующие ошибки вне файлов атома, включая FBS-сервисы, служебные cleanup-скрипты и несвязанные тесты.
- `mypy .` — FAIL: 21 существующая ошибка в 6 несвязанных файлах; `inventory_service.py` и целевой тест в выводе ошибок отсутствуют.
- `pytest -q tests/test_inventory_service_reporting_dimensions.py` — PASS: 1 passed.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии.

## Не реализовано

- Замечания ревью 1–15 по `reporting_service.py`, API и frontend не относятся к атомарному writer-контракту и намеренно не менялись.
- Новых изменений в коде не потребовалось: требование атома уже выполнено текущей реализацией `record_movement_and_adjust_balance` и покрыто целевым тестом.
- Секреты, ключи, токены и `.env` не читались.

# Фича 3

# Screen-dev report · 07-reporting

## Изменённые файлы

Атом `WarningNotice` уже реализован в сохранённом состоянии рабочей копии; в рамках этой проверки новые изменения в исходных файлах не потребовались.

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.test.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json`: не завершился; процесс остановлен после ожидания без вывода.
- `python3 scripts/ui/ui_guard.py`: красный из-за ранее существующих нарушений в `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; базовая линия не изменялась. Для `FfReportsPage.tsx` зафиксировано улучшение.
- `npm run test:unit -- --run src/ui-kit/States.test.tsx`: не запустился, локальный бинарник `vitest` отсутствует (`vitest: command not found`).

## Не реализовано

Невыполненных пунктов контракта для атома `WarningNotice` нет. Реализация использует MUI `Alert severity="warning"`, общий с `ErrorNotice` отступ `mb: 2`, пробрасывает `testId`, экспортируется из `ui-kit/index.ts`, а тест проверяет `data-testid`, роль alert, warning-класс и доступный текст.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 4

## Изменённые файлы

Атом `ReportMetricStrip` и его экспорт уже присутствуют в рабочей копии и соответствуют разрешённому набору файлов:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.test.tsx`

В рамках переделки по `REVIEW.md` относящихся к этому ui-kit-атому находок нет, поэтому исходный код этих файлов не изменялся.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локальный `tsc` отсутствует; `npx` попытался скачать пакет, но сеть недоступна (`ENOTFOUND registry.npmjs.org`).
- `python3 scripts/ui/ui_guard.py` — красный из-за новых нарушений в чужих файлах: `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. В разрешённых файлах атома нарушений не выявлено; базовую линию не обновлял.
- `npm run test:unit -- src/ui-kit/ReportMetricStrip.test.tsx` — красный: локальный `vitest` отсутствует (`vitest: command not found`).

## Не реализовано

Нет пунктов контракта, относящихся к `ReportMetricStrip`, которые не легли буквально. Находки `REVIEW.md` относятся к другим слоям и файлам карточки и не исправлялись в рамках этого атомарного куска.

# Фича 5

# DEV · 07-reporting · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.test.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json`.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py`. Новые нарушения зафиксированы в чужих файлах вне атома: `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- Красный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- src/ui-kit/MovementFlowChart.test.tsx --run`. Причина: `sh: vitest: command not found`; зависимости для frontend не установлены в этой рабочей копии.

Точная команда, выполненная ранее в составе связанной проверки: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json && npm run test:unit -- MovementFlowChart.test.tsx`.

## Не реализовано

Нет. Находка review №7, относящаяся к этому атому, исправлена: график теперь показывает пустое состояние и для непустой дневной серии, в которой все отображаемые значения равны нулю, а не рисует нулевые линии.

## Находки

- `ui_guard.py` обнаружил новые нарушения вне разрешённых файлов атома; они не изменялись.
- Установленные frontend-зависимости отсутствуют, поэтому Vitest не запускается.

# Фича 6

# DEV · 07-reporting · атом 6

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py` — `GET /reports/overview`: московская дневная агрегация, сопоставленная серия прошлого периода, пустая серия без искусственных нулей, свежесть Wildberries и предупреждения legacy-истории.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py` — служебное предупреждение legacy-истории доступно только администратору ФФ; селлер получает только предупреждение о свежести внешнего источника.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_overview.py` — API-покрытие 367 дней, аутентификации, полуоткрытой верхней границы, Moscow-дня, transfer-исключения, физического остатка, нулевой базы сравнения и принудительного seller scope.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/services/reporting_service.py app/api/reports.py tests/test_reports_overview.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy app/services/reporting_service.py app/api/reports.py` — `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_reports_overview.py` — `4 passed in 3.34s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ci/back_guard.py` — не запущен: файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- `git diff --check` — без ошибок.
- `check_migrations.py` не применим: миграция в этом атоме не добавлялась.

## Не реализовано

- Замечания ревью по таблице transfer-пар, CSV и миграционному backfill не менялись: это атомы 7, 8 и 07-A соответственно, вне границы текущего `GET /reports/overview`.
- Клиентская передача закрытой даты как полуоткрытой верхней границы, московские пресеты, отображение линии сравнения и предупреждений не менялись: это frontend-слой.

# Фича 7

# DEV · 07-reporting · атом 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py` — серверная пагинация по 50 строк, белый список сортировок, исключение внутренних transfer без фильтра склада и точечный `integrity_error` для неполных transfer-пар.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py` — параметры разрешённой сортировки для `GET /reports/inventory`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py` — API-покрытие страниц, обеих группировок, поиска по четырём полям, служебного склада, transfer и неполной пары.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && ruff check app/services/reporting_service.py app/api/reports.py tests/test_reports_inventory.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && mypy app/services/reporting_service.py app/api/reports.py` — `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend && pytest -q tests/test_reports_inventory.py` — `3 passed`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ci/back_guard.py` — не выполнен: файла `scripts/ci/back_guard.py` в этой рабочей копии нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ci/check_migrations.py` — не выполнен: файла `scripts/ci/check_migrations.py` в этой рабочей копии нет; миграций атом не добавляет.
- `git diff --check` — будет проверен перед коммитом.

## Не реализовано

- Находки review по экрану, сводке и CSV не входят в атом 7 и не менялись: это соседние frontend-атомы, атом 6 и атом 8 соответственно.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 8

# DEV · 07-reporting · атом 8

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py` — CSV строится единым агрегированным запросом и отдаётся асинхронным потоком; заголовки и поля повторяют видимую таблицу: `Товар` содержит SKU, `Название` — наименование.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py` — `GET /reports/inventory/export.csv` передаёт асинхронный поток в `StreamingResponse`, не собирая весь файл в памяти.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_csv_export.py` — добавлены проверки соответствия CSV ответу таблицы и невозможности расширить seller-область параметром `seller_id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — этот отчёт атома.

## Реализовано

- `GET /reports/inventory/export.csv` — потоковый CSV текущего авторизованного среза, с теми же фильтрами, группировкой и порядком по умолчанию, что у таблицы.
- `app.services.reporting_service.build_inventory_csv` — проверяет пустой срез и период, не длиннее 366 дней, перед началом ответа; данные не пагинируются повторными полными агрегациями.

## Миграции

Нет.

## Тесты

- `test_inventory_csv_matches_visible_product_table_columns_and_rows` — сравнивает заголовок и строку CSV с `/reports/inventory` при одинаковых параметрах.
- `test_inventory_csv_for_seller_ignores_requested_foreign_seller_scope` — подтверждает, что URL-параметр чужого селлера не раскрывает его данные пользователю селлерского портала.
- Сохранены проверки доменных ошибок пустого среза и периода более 366 дней.

## Гейты

- В каталоге `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend`: `python3 -m ruff check app/services/reporting_service.py app/api/reports.py tests/test_reports_csv_export.py` — `All checks passed!`.
- В каталоге `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend`: `python3 -m mypy app/services/reporting_service.py app/api/reports.py` — `Success: no issues found in 2 source files`.
- В каталоге `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend`: `python3 -m pytest -q tests/test_reports_csv_export.py tests/test_reports_inventory.py` — `7 passed in 6.03s`.
- В каталоге `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`: `git diff --check` — пройден без ошибок.
- `python3 scripts/ci/back_guard.py` — не выполнен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/scripts/ci/back_guard.py` в рабочей копии нет.

## Не реализовано

- Находки ревью по UI, календарю Москвы, графику и ошибочным состояниям не менялись: они лежат вне backend-слоя и файлов атома 8.
- Скрипт `back_guard.py` отсутствует в этой рабочей копии; миграций этот атом не добавляет, поэтому `check_migrations.py` неприменим.

## Блокеры

Нет. Отсутствие `scripts/ci/back_guard.py` зафиксировано в гейтах как инфраструктурная находка; реализацию и целевые проверки оно не блокирует.

Сохранение в Git не выполнено: `git add … && git commit -m "fix(reports): stream inventory csv export"` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`). Изменения остаются в рабочем дереве и требуют коммита в окружении с доступом к git-worktree metadata.

# Фича 9

# DEV · 07-reporting · атом 9

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx` — обе зарегистрированные точки маршрутизации отчёта передают экрану доступные склады, поэтому фильтр склада получает фактический список и в FF-, и в совместимом seller-маршруте.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.tsx` — основной seller-маршрут `/reports` передаёт экрану доступные склады; доступ и отсутствие селектора чужого селлера сохранены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — отчёт этого атома.

## Гейты

- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`: `git diff --check` — зелёный.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`: `npx tsc --noEmit -p tsconfig.app.json` — не запущен: локального `tsc` нет, а `npx` не смог скачать пакет из-за недоступности `registry.npmjs.org` (`ENOTFOUND`).
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting`: `python3 scripts/ui/ui_guard.py` — красный только по существующим отступлениям вне файлов атома: `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для `frontend/src/screens/ff/FfReportsPage.tsx` guard отмечает улучшение; базовая линия не менялась.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`: `npm run test:unit` — не запущен: `vitest: command not found`.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend`: `npx playwright test tests-e2e/ff-reports.spec.ts` — не запущен: локального Playwright нет, загрузка пакета невозможна из-за недоступности `registry.npmjs.org` (`ENOTFOUND`).

## Не реализовано

- В рамках атома 9 не менялись состояния, даты, API, CSV и таблица отчёта: это соседние атомы и отдельные находки `REVIEW.md`.
- Автоматические проверки не подтверждены из-за отсутствующих frontend-зависимостей и закрытой сети. Ручная проверка кода подтверждает, что маршруты остаются защищены прежними условиями `inventory` для ФФ и `products` для селлера, а seller-экран получает пустой список селлеров.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 10

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

Экран использует календарную дату Москвы для пресетов, передаёт серверу исключающую верхнюю границу следующего дня и автоматически ограничивает срез единственным складом. При смене общего среза прежние показатели и строки очищаются; при отсутствии базы сравнения показано «—» с предусмотренным пояснением. Ошибка сводки заменяет верхний блок и не оставляет старые значения видимыми. Исправлен сломанный FF e2e и добавлен сценарий селлерского маршрута без FF-фильтра и технического предупреждения.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json`
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts`
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && git diff --check`
- КРАСНЫЙ вне этого атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` сообщает новые нарушения только в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Эти файлы не входят в разрешённый слой экрана.
- КРАСНЫЙ по окружению: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit` не стартует: `sh: vitest: command not found`.

## Не реализовано

- Находки ревью № 3–5, 7–12 требуют изменений в backend-сервисах, миграции, CSV и ui-kit и не входят в разрешённые файлы screen-dev. Они не исправлялись.
- Находка № 1 о передаче складов маршрутами уже не воспроизводится в этой рабочей копии: оба маршрута передают `warehouses`; экранный дефект единственного склада исправлен в `FfReportsPage.tsx`. Фильтрация только операционных складов остаётся обязанностью источника данных.
- Отдельный файл `docs/blockers/S-33.md`, запрошенный ревью для правил экспорта, не создавался: это документационный слой вне разрешённого списка файлов текущего атома.

# Фича 11

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/docs/blockers/S-33.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

Экран использует календарную дату Москвы для пресетов, передаёт серверу исключающую верхнюю границу следующего дня и автоматически ограничивает срез единственным складом. При смене общего среза прежние показатели и строки очищаются; при отсутствии базы сравнения показано «—» с предусмотренным пояснением. Ошибка сводки заменяет верхний блок и не оставляет старые значения видимыми. В этом атоме усилена e2e-проверка: обе группировки, серверная вторая страница, неизменность сводки и CSV с MIME `text/csv`.

## Гейты

- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx tsc --noEmit -p tsconfig.app.json`
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npm run test:unit -- --run src/screens/ff/FfReportsPage.tsx`
- КРАСНЫЙ, вне файлов атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting && python3 scripts/ui/ui_guard.py` сообщает новые нарушения в `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- ЗЕЛЁНЫЙ: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend && npx playwright test tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts`
- Дополнительно: `npm run test:e2e -- tests-e2e/ff-reports.spec.ts tests-e2e/seller-reports.spec.ts` не запускает Playwright в этой рабочей копии (`error: unknown command 'test'`); целевой набор успешно выполнен прямой командой `npx playwright test` выше.
- ЗЕЛЁНЫЙ: `git diff --check`
- Не сохранено commit: `git add ... && git commit ...` не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`). Метаданные Git worktree находятся вне разрешённой на запись области этой сессии; SHA для результата отсутствует.

## Не реализовано

В рамках экранного атома 11 не менялись серверные формулы, миграция, API, маршрутизация и источники данных из находок 1–13 `REVIEW.md`: это другие файлы и слои. Тест экрана закрывает находку 14 в разрешённом слое: обе группировки, серверную вторую страницу, неизменность сводки, пустую выгрузку и MIME `text/csv`.

## Находки

Для двух явных запретов экрана добавлен обязательный реестр блокировок `docs/blockers/S-33.md`: пустой CSV-срез и период длиннее 366 дней.

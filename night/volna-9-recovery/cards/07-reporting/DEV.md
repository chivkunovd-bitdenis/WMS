# Фича 1

# Backend DEV · 07-reporting · фича 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/models/inventory_movement.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_movement_reporting_dimensions.py`

Модель и миграция добавляют `seller_id`, обязательный `warehouse_id` и флаг
`reporting_dimensions_legacy`; backfill использует связи товара и ячейки, а также
создаёт индексы tenant/seller/warehouse по времени.

## Гейты

- `ruff check app/models/inventory_movement.py tests/test_inventory_movement_reporting_dimensions.py` — PASS.
- `mypy app/models/inventory_movement.py` — PASS.
- `pytest tests/test_inventory_movement_reporting_dimensions.py` — PASS, 2 теста.
- `pytest` — НЕ ПРОЙДЕН: полный набор остановлен на существующих writer-тестах, которые создают `InventoryMovement` без `warehouse_id`; заполнение новых движений относится к фиче 2.
- `python3 scripts/ci/back_guard.py` — НЕ ЗАПУЩЕН: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — НЕ ЗАПУЩЕН: файл отсутствует в рабочей копии.

## Не реализовано

- Заполнение `seller_id` и `warehouse_id` в штатном сервисе записи движений не менялось: это отдельная фича 2 по контракту.
- Роуты и read-only API отчёта не менялись: они относятся к последующим фичам.
- Полный pytest требует завершения фичи 2, потому что текущие writer-пути ещё не передают новые обязательные измерения.

# Фича 2

# Backend DEV · 07-reporting · фича 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/inventory_service.py` — штатная точка записи движения теперь фиксирует `Product.seller_id` и `StorageLocation.warehouse_id` в `InventoryMovement`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_service_reporting_dimensions.py` — проверка неизменности измерений после перепривязки товара и ячейки.

## Гейты

- `ruff check .` — НЕ ПРОЙДЕН: 83 ранее существующих ошибки в backend; изменённые файлы проходят отдельную проверку `ruff check app/services/inventory_service.py tests/test_inventory_service_reporting_dimensions.py`.
- `mypy .` — НЕ ПРОЙДЕН: 21 ранее существующая ошибка в 6 файлах; изменённый сервис не добавляет ошибок. Отдельная проверка теста после аннотации проходит по новой проверке типов, кроме существующих ошибок в соседних файлах.
- `pytest tests/test_inventory_service_reporting_dimensions.py` — PASS, 1 тест.
- `pytest` — НЕ ПРОЙДЕН: 812 passed, 5 skipped, 2 failed. Падения в существующем `tests/test_fbs_supply_from_orders.py::test_fbs_cutoff_autoplans_supply_manual_date_and_calendar` и в `tests/test_inventory_movements_report.py::test_inventory_movements_summary_groups_and_period_filter`; второе напрямую создаёт движения без обязательного `warehouse_id` после фичи 1. Новая проверка фичи проходит.
- `python3 scripts/ci/back_guard.py` — НЕ ЗАПУЩЕН: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — НЕ ЗАПУЩЕН: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Transfer в эту карточку не входит и не изменялся.
- Миграций нет: поля и миграция добавлены фичей 1.

## Находки

- В рабочей копии уже были несвязанные изменения `night/volna-9-recovery/JOURNAL.md`; файл не изменялся.

# Фича 3

# Screen Dev · 07-reporting · WarningNotice

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.tsx` — добавлен `WarningNotice` на базе MUI `Alert` с `severity="warning"` и теми же отступами, что у `ErrorNotice`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts` — экспортирован `WarningNotice`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/States.test.tsx` — добавлен unit-тест доступного текста, `testId` и warning-класса MUI Alert.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — GREEN, exit 0.
- `python3 scripts/ui/ui_guard.py` — RED из-за трёх нарушений в несвязанных файлах: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не обновлялась.
- `npm run test:unit` — НЕ ЗАПУЩЕН: в рабочей копии отсутствует локальный бинарник `vitest` (`vitest: command not found`, exit 127).

## Не реализовано

- Пункты экрана отчётности не реализовывались: эта карточка ограничена атомом `WarningNotice`.
- Проверка unit-теста фактическим запуском не выполнена из-за отсутствия установленного `vitest`; сам тест добавлен в разрешённый файл.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- В рабочей копии обнаружены несвязанные изменения `night/volna-9-recovery/JOURNAL.md`; файл не изменялся.

# Фича 4

# Screen Dev · 07-reporting · ReportMetricStrip

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.tsx` — добавлена переиспользуемая четырёхзонная outlined-полоса показателей с единицей `шт.`, табличными цифрами, нулевыми значениями, `—` для `null` и загрузочными скелетами.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts` — экспортированы компонент и его типы.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/ReportMetricStrip.test.tsx` — добавлены unit-проверки обычных показателей, нуля, неприменимого сравнения и загрузки.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend` — GREEN, exit 0.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting` — RED: три нарушения в несвязанных файлах `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`; базовая линия не изменялась.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend` — НЕ ЗАПУЩЕН: отсутствует локальный бинарник `vitest` (`vitest: command not found`, exit 127).

## Не реализовано

- Остальные части экрана отчётности (`MovementFlowChart`, экран и маршруты) не реализовывались: текущая карточка ограничена атомом `ReportMetricStrip`.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Несвязанные изменения в `night/volna-9-recovery/JOURNAL.md` не затрагивались.

# Фича 5

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.test.tsx

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не выполнен: локального `tsc` нет, а `npx` не смог скачать пакет из-за сетевой ошибки `ENOTFOUND registry.npmjs.org`.
- `python3 scripts/ui/ui_guard.py` — красный из-за трёх новых нарушений в несвязанных файлах: `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Файлы не изменялись и baseline не обновлялся.
- `npm run test:unit -- --run src/ui-kit/MovementFlowChart.test.tsx` — не выполнен из-за отсутствующих локальных зависимостей (`node_modules/.bin/vitest` отсутствует); запуск общей команды остановился на недоступном npm registry.

## Не реализовано

- Пункты контракта для этого атома реализованы: обычное состояние, видимая легенда, доступное описание, условная пунктирная серия сравнения, пустой период и skeleton при загрузке.

# Фича 6

# Backend Dev · 07-reporting · защищённая сводка

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py` — агрегация сводки, полуоткрытый период, сравнение с предыдущим интервалом и дневные серии.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py` — read-only `GET /reports/overview` с tenant/seller scope и проверкой прав.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/main.py` — регистрация роутера отчётов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_overview.py` — проверки авторизации и отказа при периоде длиннее 366 дней.

## Реализовано

- `GET /reports/overview` возвращает текущий остаток, внешний приход/расход, сравнение с предыдущим равным интервалом, дневные серии, `generated_at`, свежесть источника и предупреждения.
- Даты обрабатываются как полуоткрытый интервал `[date_from, date_to)`; интервал длиннее 366 дней отклоняется.
- Внутренние движения исключаются из потоковых итогов по `transfer_group_id`; seller-пользователь ограничивается своим seller scope, а доступ проверяется через существующий `inventory`/`can_products` guard.

## Гейты

- `ruff check app/services/reporting_service.py app/api/reports.py tests/test_reports_overview.py app/main.py` — GREEN.
- `mypy app/services/reporting_service.py app/api/reports.py` — GREEN.
- `pytest -q tests/test_reports_overview.py` — GREEN, 2 passed.
- `ruff check .` — RED на 87 существующих нарушениях в несвязанных файлах; собственные файлы проходят.
- `mypy .` — не выполнен после полного ruff, целевой mypy для изменённых модулей GREEN.
- `pytest` — полный набор не выполнен; целевые тесты GREEN.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии.

## Не реализовано

- Поле `Warehouse.is_operational` отсутствует в текущей схеме и не входит в разрешённые файлы этого атома; текущий расчёт остатка использует строки `InventoryBalance` через существующие склады. Добавление поля/миграции оставлено следующей зависимой фиче.
- Свежесть внешнего Wildberries-источника не подключалась: в ответе возвращается `null`, предупреждения пусты, так как контракт не указал существующий источник этой метрики.
- Полный tenant/seller сценарий с transfer-парами не добавлялся в тесты этого атома; фильтрация `transfer_group_id` реализована в сервисе.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Несвязанные изменения в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/JOURNAL.md` не затрагивались.

# Фича 7

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py — постраничная агрегация отчёта по товарам и операциям, поиск, складской scope и диагностика неполной transfer-пары.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py — `GET /reports/inventory`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_inventory.py — проверки API, группировок и фиксированного размера страницы.

## Гейты

- ruff: GREEN — целевые backend-файлы прошли `ruff check`.
- mypy: GREEN — `app/services/reporting_service.py` и `app/api/reports.py`.
- pytest: GREEN — `tests/test_reports_inventory.py`, 2 passed.
- back_guard.py: BLOCKED — файл отсутствует в рабочей копии; запуск из backend и корня невозможен.
- check_migrations.py: BLOCKED — файл отсутствует в рабочей копии; запуск из backend и корня невозможен.

## Не реализовано

- Текущий остаток в строке товара не добавлен: API отдаёт `in_qty`, `out_qty` и `net`, а источник балансов требует отдельного согласования контракта 07-A.
- Полное различение служебного склада по `is_operational` невозможно: колонка отсутствует в текущей модели; применён существующий legacy-признак `FBS WB `.

# Фича 8

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py — добавлен полный CSV-срез с теми же фильтрами, группировкой, сортировкой и seller scope, что у таблицы.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py — добавлен потоковый `GET /reports/inventory/export.csv` с CSV MIME type и доменными ошибками.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_csv_export.py — проверки пустого среза и периода длиннее 366 дней.

## Гейты

- ruff: GREEN для изменённых backend-файлов; полный `ruff check .` BLOCKED существующими 82 нарушениями в несвязанных файлах.
- mypy: GREEN для `app/api/reports.py` и `app/services/reporting_service.py`.
- pytest: GREEN — целевые CSV и inventory тесты, 4 passed.
- back_guard.py: BLOCKED — `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- check_migrations.py: BLOCKED — `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии.

## Не реализовано

- Поля текущего остатка в строках CSV не добавлялись: экспорт повторяет фактические агрегированные колонки существующего `/reports/inventory`, согласно зависимости от фичи 7.
- Полный тест с заполненными движениями и сравнением CSV с таблицей не добавлен: доступные API-фабрики карточки создают только пользователя, без данных отчёта; добавлены проверки доменных отказов.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 9

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/App.tsx — маршрут `/app/ff/reports` оставлен доступным только администратору ФФ или пользователю с правом `inventory`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/layouts/AuthedAppLayout.tsx — пункт «Отчёты» показывается администратору ФФ или пользователю с правом `inventory`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/screens.registry.json — зарегистрирован единый экран `S-33` с маршрутами FF и seller.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `frontend/`) — GREEN.
- `python3 scripts/ui/ui_guard.py` (из корня) — RED/BLOCKED: скрипт сообщил о новых нарушениях в несвязанных файлах `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия флагом `--update` не изменялась.
- `npm run test:unit` (из `frontend/`) — BLOCKED: команда не запускается, поскольку в рабочей копии отсутствует `vitest` (`sh: vitest: command not found`).
- `python3 -m json.tool frontend/screens.registry.json` — GREEN.

## Не реализовано

- Фактический маршрут и пункт меню `/app/seller/reports` не подключены: портал селлера собирается через отдельные `frontend/src/apps/seller/SellerApp.tsx` и `frontend/src/apps/seller/SellerLayout.tsx`, но контракт этой карточки разрешает изменять только `App.tsx`, `AuthedAppLayout.tsx` и `screens.registry.json`. Правка запрещённых файлов нарушила бы границы screen-dev.
- Живой Playwright-проверкой сценарии не прогонялись: в контракте для этой карточки нет разрешённого e2e-файла, а seller-маршрут требует правки запрещённых файлов.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 10

# Screen Dev · 07-reporting · фича 10

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

Экран переведён на контрактную шапку, `FilterBar`, единый запрос сводки и таблицы, `ReportMetricStrip`, `MovementFlowChart`, freshness/warning и частичные ошибки. Старые числа сбрасываются в loading-состояние при смене фильтра. Seller-фильтр рендерится только для ФФ-контекста с переданным списком селлеров.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — GREEN (команда завершилась без диагностик).
- `python3 scripts/ui/ui_guard.py` из корня — RED из-за существующих/несвязанных нарушений: `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для `FfReportsPage.tsx` стало лучше: ручные кнопка и таблица устранены.
- `npm run test:unit` из `frontend/` — НЕ ЗАПУЩЕН: отсутствует локальный бинарник `vitest` (`vitest: command not found`, exit 127).

## Не реализовано

- Seller e2e-файл не добавлялся: в рабочем checkout отсутствует доступный seller fixture/сценарий авторизации, а разрешённые файлы карточки не включают общие seller helpers. Сам экран скрывает seller-фильтр при пустом списке `sellers`.
- Серверный export CSV и переключатель группировки не добавлены в эту атомарную фичу: они относятся к последующим пунктам FEATURES.md.

# Фича 11

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx`

Добавлены серверная группировка «По товарам / По операциям», постраничная загрузка по 50 строк, строка диапазона, переходы между страницами и скачивание серверного CSV. Переключение таблицы не перезагружает верхнюю сводку. Файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/seller-reports.spec.ts` отсутствует в рабочей копии, поэтому не изменялся.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` (из `frontend/`) — зелёный.
- `python3 scripts/ui/ui_guard.py` (из корня) — красный: guard сообщил новые нарушения в чужих файлах `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/components/WbProductPickerDialog.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Разрешённые файлы карточки не расширял.
- `npm run test:unit` (из `frontend/`) — не запустился: `vitest: command not found`.

## Не реализовано

- E2E-проверки фичи 11 в `ff-reports.spec.ts` и `seller-reports.spec.ts` не добавлялись: роль ограничена экраном, а seller spec отсутствует; существующий FF spec не входит в текущую разрешённую карту файлов реестра.

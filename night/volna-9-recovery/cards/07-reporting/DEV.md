# Фича 1

# Backend-dev · 07-reporting · атом 1

## Изменённые файлы

- Изменений в backend-файлах по результатам re-review не потребовалось: замечания REVIEW.md относятся к 07-B reporting API/UI, а не к 07-A модели и миграции.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/models/inventory_movement.py` — проверен контракт `seller_id`, обязательный `warehouse_id` и `reporting_dimensions_legacy`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py` — проверен backfill коррелированными подзапросами, отказ при неразрешимом `warehouse_id`, внешние ключи и составные индексы.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_inventory_movement_reporting_dimensions.py` — проверены модель и текстовые инварианты миграции.

## Гейты

- `ruff check .` — FAIL: 82 уже существующих ошибок в несвязанных backend-файлах; ошибок в перечисленных файлах атома в выводе нет.
- `mypy .` — FAIL: 21 уже существующая ошибка в 6 несвязанных файлах; ошибок в перечисленных файлах атома нет.
- `pytest -q tests/test_inventory_movement_reporting_dimensions.py` — PASS, 2 passed.
- `pytest` — не запускался целиком после целевого теста: полный backend уже блокируется перечисленными ruff/mypy-ошибками.
- `python3 scripts/ci/back_guard.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/scripts/ci/back_guard.py` в этой рабочей копии нет.
- `python3 scripts/ci/check_migrations.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/scripts/ci/check_migrations.py` в этой рабочей копии нет.

## Не реализовано

- Находки 1–15 из REVIEW.md, относящиеся к `reporting_service.py`, frontend, UI-реестру, E2E и `docs/blockers`, не реализовывались: они находятся вне атома 07-A и вне роли backend-dev для указанных трёх файлов.
- Полное применение миграции к живой базе не выполнялось: для этого в рабочей копии нет предусмотренного migration guard/тестового окружения; секреты, `.env`, ключи и кабинеты учётных данных не читались.

## Находки

- В текущей рабочей копии обязательные guard-скрипты отсутствуют по указанным путям.

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

## Изменённые файлы

Изменений в исходных файлах атома нет: `MovementFlowChart` уже реализован в соответствии с контрактом, экспортирован через ui-kit и покрыт требуемыми unit-сценариями.

Проверенные файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/ui-kit/MovementFlowChart.test.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный из-за четырёх новых нарушений в несвязанных файлах: `frontend/src/App.tsx`, `frontend/src/components/WbProductPickerDialog.tsx`, `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`, `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовую линию не обновлял.
- `npm run test:unit -- --run frontend/src/ui-kit/MovementFlowChart.test.tsx` — не запущен: в `frontend` отсутствует локальный исполняемый `vitest` (`node_modules` не установлен).

Проверены сценарии контракта: видимая легенда и доступное описание серий, отсутствие пунктирной серии при выключенном сравнении, сообщение «За выбранный период движений нет» и отдельный скелет при загрузке.

## Не реализовано

- Замечание ревью о том, что экран/API не передают предыдущую дневную серию, не исправлялось: оно относится к `FfReportsPage` и backend, а не к разрешённым файлам атома `MovementFlowChart`.
- Полный зелёный `ui_guard.py` невозможен без правок четырёх чужих экранов или обновления базовой линии; оба действия выходят за границы атома.
- Unit-тест не подтверждён запуском из-за отсутствующего `vitest`; установка зависимостей не выполнялась.

# Фича 6

# DEV — 07-reporting

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md`

Исправлен backend-слой отчёта: дневная серия явно соединяет склад, корректно включает последний календарный день для неполуночного `date_to`, текущий остаток товарной строки ограничивается текущим `Product.seller_id`, а целостность transfer-пары проверяет состав пары, склады, направление и количество.

## Гейты

- `ruff check` по изменённым backend-файлам: PASS.
- `mypy` по изменённым сервису и API: PASS (`Success: no issues found in 2 source files`).
- `pytest` по `test_reports_overview.py` и `test_reports_inventory.py`: PASS (`4 passed`).
- Полный `ruff check .`: FAIL на 82 существующих ошибках в несвязанных файлах; изменённые файлы проходят.
- Полный `mypy .` и полный `pytest`: не запускались после остановки цепочки полным ruff.
- `python3 scripts/ci/back_guard.py`: недоступен — файла `scripts/ci/back_guard.py` нет в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py`: недоступен — файла `scripts/ci/check_migrations.py` нет в этой рабочей копии.

## Не реализовано

- Фильтрация по `Warehouse.is_operational` и вычисление `source_freshness`/legacy-предупреждения не добавлены: в этой рабочей копии нет поля `Warehouse.is_operational`, миграции для него или канонической модели времени успешного импорта WB. Эвристика по имени склада намеренно не расширялась.
- Frontend-находки из REVIEW.md не реализовывались: роль ограничена backend-dev.

## Блокеры

Нет.

# Фича 7

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py` — исправлена проверка целостности transfer-пар при фильтре склада: для проверки читаются обе стороны пары, но в выдачу по-прежнему попадают только строки выбранного среза.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — этот отчёт.

## Гейты

- `ruff`: FAIL на существующих несвязанных нарушениях в backend (82 ошибки; reporting_service.py в списке нарушений отсутствует).
- `mypy`: FAIL на существующих несвязанных ошибках в 6 файлах; reporting_service.py и reports.py в списке нарушений отсутствуют.
- `pytest`: целевой `tests/test_reports_inventory.py` — `2 passed`; полный `pytest` запущен, итог ожидается из процесса.
- `back_guard.py`: не запущен — в этой рабочей копии отсутствует `scripts/ci/back_guard.py`.
- `check_migrations.py`: не запущен — в этой рабочей копии отсутствует `scripts/ci/check_migrations.py`.

## Не реализовано

- Использование `Warehouse.is_operational` из ARCH-CROSS не легло буквально: в текущей рабочей копии у модели `Warehouse` и в миграциях нет такого поля. Существующий код сохраняет legacy-ограничение по префиксу `FBS WB `; добавление новой колонки и миграции выходит за перечисленные файлы атома.
- Остальные frontend-находки из REVIEW.md не относятся к роли backend-dev и не изменялись.

# Фича 8

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/models/warehouse.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/alembic/versions/20260822_0095_warehouse_operational_flag.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_csv_export.py`

## Гейты

- `ruff check` по изменённым backend-файлам — пройден после форматирования.
- `mypy` по изменённым model/service/api — пройден.
- `pytest -q backend/tests/test_reports_csv_export.py` — пройдено, 2 passed.
- `python3 scripts/ci/back_guard.py` — не запущен: скрипт отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — не запущен: скрипт отсутствует в этой рабочей копии.
- Полный `ruff check .` — не пройден из-за 83 ранее существующих нарушений вне изменённых файлов.

## Не реализовано

- API-эндпоинт CSV уже был добавлен предыдущим атомом; в этом проходе исправлены общие backend-фильтры, от которых зависит его честное совпадение с таблицей.
- Дополнительная seeded-проверка строк CSV с непустым срезом не добавлялась: текущие API-тесты создают только организацию без складских движений.
- Обнаруженные в окружении отсутствующие guard-скрипты не восстанавливались, чтобы не расширять атом.
- Коммит невозможен в текущем sandbox: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`). Изменения остаются в этой рабочей копии и требуют коммита владельцем окружения.

## Находки

- Секреты, токены, `.env` и кабинеты учётных данных не читались.

# Фича 9

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerApp.tsx` — добавлен защищённый маршрут `/app/seller/reports` для селлера с `can_products`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/apps/seller/SellerLayout.tsx` — пункт «Отчёты» показывается только при праве `products`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` — колонка «Селлер» скрыта в seller-портале, где список селлеров пуст.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/screens.registry.json` — `S-33` дополнен фактически изменяемым экранным файлом.

## Гейты

- `python3 -m json.tool frontend/screens.registry.json` — зелёный.
- `git diff --check` — зелёный.
- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: локальный бинарник `tsc` отсутствует, загрузка через `npx` недоступна.
- `npm run test:unit` — не подтверждён: локальный бинарник `vitest` отсутствует.
- `python3 scripts/ui/ui_guard.py` — красный из-за нарушений в несвязанных `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; для `FfReportsPage.tsx` guard зафиксировал улучшение (`своя-кнопка` и `своя-таблица`: 1 → 0). Базовая линия не изменялась.

## Не реализовано

- Полный Playwright-прогон не выполнен: в окружении отсутствуют локальные frontend-зависимости; маршруты и условия доступа проверены по коду.
- Остальные находки `REVIEW.md` относятся к backend/API или другим атомам и в этот screen-dev проход не входят.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 10

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx` — исправлены экранные находки ревью: добавлен опциональный фильтр склада, пресет «Другой период» с условным раскрытием дат, передача `warehouse_id`, подавление ошибок отменённых запросов, независимая загрузка таблицы при пагинации, поддержка предыдущей серии графика и блокировка повторного CSV с состоянием формирования.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/cards/07-reporting/DEV.md` — этот отчёт.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — команда запущена из `frontend/`; завершилась без диагностик.
- `python3 scripts/ui/ui_guard.py` — команда запущена из корня; отдельного диагностического вывода от объединённого запуска не получено.
- `npm run test:unit` — команда запущена из `frontend/`; отдельного диагностического вывода от объединённого запуска не получено.
- `python3 -m json.tool frontend/screens.registry.json` — зелёный.
- `git diff --check` — зелёный.

## Не реализовано

- Передача фактического списка складов в экран не расширялась через `App.tsx` и `SellerApp.tsx`, поскольку эти файлы не входят в разрешённый список текущего screen-dev атома. Компонент принимает `warehouses`; при его отсутствии фильтр корректно скрыт.
- Предыдущая дневная серия отображается только если backend возвращает `previous_out_qty`; добавление этого поля в backend относится к другой роли и слою.
- Полный Playwright-прогон не выполнен: в рабочем окружении команда не предоставила диагностического результата до завершения ночного лимита.
- Коммит невозможен в текущем sandbox: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-07-reporting1/index.lock` (`Operation not permitted`).

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 11

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/src/screens/ff/FfReportsPage.tsx — отмена устаревших табличных запросов, стабильные test id для пагинации.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/frontend/tests-e2e/ff-reports.spec.ts — обновлены проверки под текущий DataTable, группировки, пагинации, неизменности сводки и CSV.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: локальный пакет `tsc` отсутствует; `npx` попытался скачать его, но сеть недоступна (`ENOTFOUND registry.npmjs.org`).
- `python3 scripts/ui/ui_guard.py` — красный из-за четырёх новых нарушений вне файлов этой карточки: `src/App.tsx`, `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx`, `src/screens/v2/SellerInboundDraftScreen.tsx`. Для `FfReportsPage.tsx` guard зафиксировал улучшение: своя кнопка и своя таблица устранены.
- `npm run test:unit` — красный: `vitest: command not found`.

## Не реализовано

- Backend-находки из ревью (дневная агрегация, складская область, transfer integrity и свежесть данных) не относятся к роли `screen-dev` и к атомарной фиче 11; backend-файлы не изменялись.
- Живой Playwright-прогон невозможен в текущем окружении без установленных frontend-зависимостей; сценарий обновлён статически под текущие UI-селекторы.

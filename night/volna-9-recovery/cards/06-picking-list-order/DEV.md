# Фича 1

## Изменённые файлы

В рамках этого прохода файлы ui-kit не изменялись: реализация атома уже содержит требуемые состояния и экспортируется через `frontend/src/ui-kit/index.ts`.

Проверенные файлы:

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/ModalFrame.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/FilterBar.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Cells.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Actions.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/UiKitShowcase.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не завершён: процесс завис без вывода и остановлен вручную; ранее локальный `tsc` также отсутствовал.
- `python3 scripts/ui/ui_guard.py` — красный из-за двух новых нарушений вне атома: `frontend/src/components/WbProductPickerDialog.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не изменялась; для `FfFbsPickList.tsx` нарушений стало меньше.
- `npm run test:unit -- --run src/ui-kit` — не запущен: `vitest: command not found`.

## Не реализовано

- Находки 1–7 из `REVIEW.md` относятся к `FfFbsPickList.tsx`, `FbsPrintPreviewDialog.tsx`, API и backend; эти файлы не входят в разрешённую границу screen-dev и не изменялись.
- Живой browser-review не выполнялся: задача ограничена переиспользуемыми ui-kit элементами, а frontend-зависимости для unit-тестов отсутствуют.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 2

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md

Модель `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/models/fbs_supply.py` уже содержит канонический `relationship.order_by`: `wb_order_id`, затем `order.id`; в этой переделке она не требовала изменения. Тест явно фиксирует обе части сортировки, включая развязку одинакового marketplace-номера внутренним ID.

## Гейты

- `ruff check .` — FAIL: 82 существующие ошибки в backend, включая `app/api/fbs_sellers.py`, `app/services/fbs_stock_sync_service.py` и другие файлы вне атома; ошибок в изменённом тесте не показано.
- `mypy .` — FAIL: существующие ошибки типов в сервисах и скриптах вне атома (`inventory_movement_report_service.py`, `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и другие).
- `pytest backend/tests/test_fbs_supply_assembly.py` — PASS: 17 passed, 1 skipped.
- `python3 scripts/ci/back_guard.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/check_migrations.py` отсутствует; миграций в атоме нет.

## Не реализовано

- Находки 1–6 из `REVIEW.md` относятся к frontend и другим backend-сервисам печати, а не к атомарному куску 2 и его разрешённым файлам; они не менялись.
- Для модели миграция не нужна.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 3

# DEV · 06-picking-list-order · атом 3

## Изменённые файлы

В рамках переделки по REVIEW.md backend-файлы атома не изменялись: серверная реализация уже присутствует в рабочей копии и соответствует контракту.

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py` — `get_picking_list` строит группы по `(article, sku_code, size, product_name)`, сортирует группы и заказы детерминированно, считает непрерывные номера и полный `order_ids`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py` — endpoint `GET /operations/fbs-supplies/{supply_id}/picking-list` отдаёт `number_start`, `number_end` и `order_ids`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — интеграционный сценарий проверяет несколько товарных групп, диапазоны, канонический состав и повторный идентичный запрос.

Находки REVIEW.md 1–6 относятся к frontend и печати следующего атома; находка 7 требует проверки `order-print-tape` из атома 4, поэтому в этот backend-атом не включалась.

## Гейты

- `ruff check .` — FAIL: 82 существующие ошибки в несвязанных файлах backend (в том числе `app/api/fbs_sellers.py`, `app/services/fbs_stock_sync_service.py`, scripts и других тестах); файлы атома не указаны в выводе.
- `mypy .` — FAIL: 21 существующая ошибка в 6 несвязанных файлах (`inventory_movement_report_service.py`, `wildberries_credentials_service.py`, cleanup-скрипты, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`, `wildberries_product_import_service.py`).
- `pytest tests/test_fbs_supply_assembly.py` — PASS: `17 passed, 1 skipped`.
- `python3 scripts/ci/back_guard.py` — NOT RUN: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — NOT RUN: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Исправления frontend-печати, предпросмотра, состояний `shortage/order_errors` и browser/e2e-проверки не реализованы: они находятся за пределами backend-атома 3.
- Новых миграций нет.
- Новых backend-изменений не потребовалось: REVIEW.md подтверждает, что серверный порядок, диапазоны, tenant-фильтр и повторяемость уже работают.

# Фича 4

# Backend development report · 06-picking-list-order

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_packaging_integration.py` — добавлен endpoint-регресс: полный состав в перемешанном порядке возвращается канонически, повторная печать сохраняет порядок и номера.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — этот отчёт.

## Гейты

- `ruff check .` — не пройден: 82 ранее существующие ошибки за пределами изменённого теста; новая проверка не добавила диагностик.
- `mypy .` — не пройден: 21 ранее существующая ошибка в 6 файлах, изменённый тест и backend-атом в списке ошибок отсутствуют.
- `pytest -q tests/test_fbs_packaging_integration.py -k tape_covers_every_order_and_matches_picking_list` — пройден, `1 passed`.
- `pytest -q` — запущен полный набор; к моменту формирования отчёта процесс ещё выполнялся (дошёл минимум до 26% без падений).
- `python3 scripts/ci/back_guard.py` — недоступен в этой рабочей копии: файл отсутствует.
- `python3 scripts/ci/check_migrations.py` — недоступен в этой рабочей копии: файл отсутствует.

## Не реализовано

- Новые backend-роуты, модели и миграции не требовались: endpoint `/operations/fbs-supplies/{supply_id}/order-print-tape` уже канонизирует полный входной набор и возвращает постоянные `order_number`, включая номера в `order_errors` для пропущенных WB-стикеров.
- Живые WB-запросы не выполнялись; тест использует существующую изолированную заглушку.

## Блокеры

- Полные ruff/mypy-гейты заблокированы накопленными ошибками baseline; guard-скрипты отсутствуют в checkout.

# Фича 5

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — красный: в рабочей копии отсутствует локальный `tsc`, а сеть недоступна для загрузки пакета (`ENOTFOUND registry.npmjs.org`).
- `python3 scripts/ui/ui_guard.py` — красный из-за существующих нарушений вне атома: `frontend/src/components/WbProductPickerDialog.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для затронутого `FfFbsSupplyWorkspace.tsx` нового нарушения после правки нет.
- `npm run test:unit` — красный: отсутствует локальный `vitest` (`sh: vitest: command not found`).

## Не реализовано

- Полный Playwright-сценарий из контракта не запускался: frontend-зависимости в этой рабочей копии не установлены.
- Физическая серверная выдача полных ID и полей порядка не изменялась: атом ограничен тремя frontend-файлами, указанными в контракте.

# Фича 6

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/fbsApi.ts
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.test.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный из-за двух посторонних нарушений: `src/components/WbProductPickerDialog.tsx` (экран-монолит 0 → 646) и `src/screens/v2/SellerInboundDraftScreen.tsx` (1111 → 1169). В целевом `FfFbsPickList.tsx` новые нарушения устранены; базовую линию не обновлял.
- `npm run test:unit -- --run src/screens/v2/FfFbsPickList.test.ts` — не запущен: в рабочей копии отсутствует бинарник `vitest` (`sh: vitest: command not found`).

## Не реализовано

- Полные Playwright-сценарии `S-03-TC-001…007` не добавлял: исправление ограничено экраном, API-типами и существующим unit-тестом; окружение frontend не содержит зависимостей для их запуска.
- Backend не изменял: сервер уже возвращает канонические `number_start`, `number_end`, `order_ids` и данные WB-стикера в ответе `order-print-tape`.

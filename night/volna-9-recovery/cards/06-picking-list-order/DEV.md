# Фича 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/ModalFrame.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Actions.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/UiKitShowcase.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не пройдено: локальный TypeScript не установлен, `npx` не смог скачать пакет из-за `ENOTFOUND registry.npmjs.org`.
- `python3 scripts/ui/ui_guard.py` — не пройдено: обнаружены новые нарушения в несвязанных и не изменённых файлах `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/components/WbProductPickerDialog.tsx` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Базовая линия не изменялась.
- `npm run test:unit` — не пройдено: `vitest: command not found`.

## Не реализовано

- Находки 1–7 из `REVIEW.md` относятся к backend и экрану S-03, а не к разрешённому атомарному UI-kit куску; эти файлы не изменялись.
- В пределах UI-kit исправлены состояния `busy`: системное закрытие `ModalFrame` блокируется, а `PrintAction` показывает индикатор и понятную причину недоступности.

# Фича 2

# DEV · 06-picking-list-order · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/models/fbs_supply.py` — relationship `orders` упорядочивает заказы по `wb_order_id`, затем по внутреннему `order.id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — интеграционная проверка стабильного порядка и проверка обоих ключей relationship.

## Гейты

- `ruff check .` — FAIL: 82 уже существующие ошибки в backend, в изменённых файлах ошибок не выявлено.
- `mypy .` — FAIL: 21 уже существующая ошибка в 6 других файлах, изменённые файлы в выводе отсутствуют.
- `pytest -q tests/test_fbs_supply_assembly.py` — PASS: 14 passed, 1 skipped.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в этой рабочей копии.

## Не реализовано

- Других пунктов контракта не реализовывалось: выполнен только атомарный backend-кусок стабильного порядка relationship поставки.
- Миграции не нужны.
- Коллизия `wb_order_id` не может быть создана через текущую БД-тестовую схему из-за уникального ограничения `(seller_id, wb_order_id)`; tie-breaker зафиксирован проверкой конфигурации relationship, а реальная выдача проверена интеграционным тестом.

# Фича 3

# DEV · 06-picking-list-order · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — усилен реальный API-тест `GET /operations/fbs-supplies/{supply_id}/picking-list`: поставка собирается в перемешанном порядке, проверяются канонические товарные группы, полный `order_ids`, непрерывные диапазоны и повторяемость ответа.

## Гейты

- `ruff check .` — FAIL: 83 существующие ошибки backend; одна ошибка в изменённом тесте исправлена, после этого целевой тестовый файл без новых замечаний.
- `mypy .` — FAIL: 21 существующая ошибка в 6 других файлах; изменённые файлы в выводе отсутствуют.
- `pytest -q tests/test_fbs_supply_assembly.py` — PASS: 15 passed, 1 skipped.
- `pytest -q` — RUNNING при формировании артефакта; целевой набор прошёл.
- `python3 scripts/ci/back_guard.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Находки ревью про `order-print-tape` относятся к атомам 4–6 и не изменялись в рамках атомарного backend-куска 3.
- Миграции не нужны: изменены только тесты, схема базы не менялась.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 4

# Backend-dev · 06-picking-list-order

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py — разрешён выбор подмножества заказов для существующей строковой печати; порядок и `order_number` вычисляются по полной канонической поставке.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py — тесты одиночной печати с сохранением полного номера и отказа для заказа вне поставки.

## Гейты

- ruff — целевые файлы: PASS (`ruff check app/services/fbs_order_tape_print_service.py tests/test_fbs_supply_assembly.py`); полный запуск репозитория: FAIL на существующих несвязанных нарушениях.
- mypy — FAIL на существующих несвязанных ошибках в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; ошибок в изменённых файлах не показано.
- pytest — PASS: `17 passed, 1 skipped` (`tests/test_fbs_supply_assembly.py`).
- back_guard.py — не запущен: файл отсутствует в этой рабочей копии.
- check_migrations.py — не запущен: файл отсутствует в этой рабочей копии.
- git diff --check — PASS.

## Не реализовано

- UI-находки ревью не реализовывались: они относятся к роли screen-dev и не входят в API и данные этого атома.
- Генерация отдельной WMS-этикетки в физическом print-preview не изменялась: текущий backend-атом сохраняет серверные номера и обработку ошибок получения WB-стикеров.

# Фича 5

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx — полная печать получает свежий серверный состав поставки; построчный запрос сохраняет переданный набор ID.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx — служебная этикетка WMS выводится только для заказных стикеров и включается отдельной страницей в печать; пропущенные стикеры показываются через ErrorNotice.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не выполнен: в рабочей копии нет локального `tsc`, а сетевой fallback завершился `ENOTFOUND registry.npmjs.org`.
- `python3 scripts/ui/ui_guard.py` — красный из-за двух существующих нарушений вне атома: `frontend/src/components/WbProductPickerDialog.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для изменённого `FfFbsSupplyWorkspace.tsx` нового нарушения после правки нет.
- `npm run test:unit` — не выполнен: `vitest: command not found`.
- `git diff --check` — зелёный.

## Не реализовано

- Полный живой browser-сценарий и unit-тесты предпросмотра не подтверждены: в окружении отсутствуют frontend-зависимости, поэтому проверить их запуском невозможно.
- Находки ревью по `FfFbsPickList.tsx`, backend и серверной ручке не изменялись: они находятся вне трёх файлов этого атома и его разрешённой границы.

# Фича 6

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.test.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не получил завершения: процесс завис без вывода и был остановлен.
- `python3 scripts/ui/ui_guard.py` — красный из-за двух новых нарушений вне границы атома: `frontend/src/components/WbProductPickerDialog.tsx` и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx`. Для `FfFbsPickList.tsx` нарушений стало меньше.
- `npm run test:unit -- --run src/screens/v2/FfFbsPickList.test.ts` — не запущен: `vitest: command not found`.
- Commit — не создан: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` из-за ограничения доступа рабочей среды.

## Не реализовано

- E2E-сценарии `S-03-TC-001…007` в этом проходе не добавлялись: для их полноценного запуска в рабочей копии отсутствует установленный test runner, а существующий e2e-файл не содержит подготовленного сценария открытия модалки листа подбора.
- В пределах разрешённых файлов печать переведена на канонический `order-print-tape` и блокируется на время подготовки; отдельная существующая preview-компонента и серверные типы не изменялись, поскольку они не входят в границу атома.

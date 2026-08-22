# Фича 1

# DEV · 06-picking-list-order · атом 1 · переделка

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Actions.tsx` — вариант `PrintAction` со значением `стикеры заказов` теперь показывает контрактную подпись `Печать стикеров`, а не неграмматичное `Печать стикеры заказов`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/PickingListPrimitives.test.ts` — добавлена изолированная проверка `ModalFrame`, `ChoiceFilter`, `CheckCell` и `PrintAction`: блокировка закрытия при `busy`, выбор фильтра, недоступные состояния с причиной и печать стикеров заказов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — записан отчёт переделки атома.

Остальные разрешённые файлы атома уже содержат требуемые `ModalFrame`, `ChoiceFilter`, `CheckCell`, их экспорты и состояния в `UiKitShowcase`; повторных изменений им не потребовалось.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — красный из-за среды: локального `tsc` нет, а `npx` не смог обратиться к `registry.npmjs.org` (`ENOTFOUND`).
- `python3 scripts/ui/ui_guard.py` из корня рабочей копии — красный только на двух существующих файлах вне атома: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/components/WbProductPickerDialog.tsx` (`экран-монолит 0 → 646`) и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/SellerInboundDraftScreen.tsx` (`экран-монолит 1111 → 1169`). Для `FfFbsPickList.tsx` храповик сообщил три улучшения; новых нарушений в UI-kit нет. Базовая линия не менялась.
- `npm run test:unit` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — красный из-за среды: локальный `vitest` отсутствует (`sh: vitest: command not found`). Тест добавлен, но выполнить его в этой рабочей копии невозможно без установленных зависимостей.
- `git diff --check` для изменённых файлов атома — зелёный.
- `git commit -m "fix(ui-kit): verify picking list primitives"` — красный из-за ограничений рабочей среды: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` (`Operation not permitted`). Изменения локально реализованы, но отдельный восстанавливаемый commit SHA не создан.

## Не реализовано

- Находки 1–4 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/REVIEW.md` относятся к подключению продуктовой модалки, физической ленте с DataMatrix и тестам экрана в `FfFbsSupplyWorkspace.tsx`, `FfFbsPickList.tsx` и `FfFbsPickList.test.ts`. Эти файлы принадлежат последующим атомам и не входят в заданный слой переиспользуемых элементов, поэтому в атоме 1 они не менялись.
- Буквально прогнать новый unit-тест не удалось только из-за отсутствующего локального `vitest`; результат теста не объявляется зелёным.
- Сохранить переделку отдельным Git-коммитом не удалось из-за запрета записи в общие метаданные worktree; до коммита изменения остаются уязвимыми к потере.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 2

# Backend Dev · 06-picking-list-order · атом 2 · переделка

## Что реализовано

- Эндпоинты: новых нет; существующая загрузка поставки получает `orders` из relationship в стабильном порядке.
- Сервисы: новых и изменённых нет.
- Модель: `FbsSupply.orders` упорядочивает заказы по `FbsOrder.wb_order_id`, затем по `FbsOrder.id`.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/models/fbs_supply.py` — реализация атома уже сохранена в ветке: relationship `FbsSupply.orders` содержит `order_by="(FbsOrder.wb_order_id, FbsOrder.id)"`; переделка после ревью не потребовала изменения модели.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — реализация атома уже сохранена в ветке: интеграционный тест вставляет заказы с одинаковым `wb_order_id` в порядке, обратном их внутренним UUID, загружает поставку через API и проверяет развязку по `order.id`; отдельный тест фиксирует состав `order_by`; переделка после ревью не потребовала изменения теста.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — записан отчёт переделки атома и результаты повторных целевых проверок.

## Миграции

- Нет: схема базы данных не менялась.

## Тесты

- `test_fbs_supply_orders_are_returned_in_stable_order` — проверяет фактическую загрузку relationship для одинакового `wb_order_id` при обратном порядке вставки внутренних идентификаторов и ожидает сортировку по `order.id`.
- `test_fbs_supply_relationship_orders_by_wb_id_then_internal_id` — проверяет, что relationship содержит оба уровня сортировки в требуемой последовательности.

## Гейты

- `ruff check app/models/fbs_supply.py tests/test_fbs_supply_assembly.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено: `All checks passed!`.
- `mypy app/models/fbs_supply.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено: `Success: no issues found in 1 source file`.
- `pytest -q tests/test_fbs_supply_assembly.py -k 'orders_are_returned_in_stable_order or relationship_orders_by_wb_id_then_internal_id'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено: `2 passed, 17 deselected in 4.54s`.
- `python3 scripts/ci/back_guard.py` — не применим: атом не добавляет и не меняет роут.
- `python3 scripts/ci/check_migrations.py` — не применим: атом не добавляет миграцию.
- `git diff --check -- night/volna-9-recovery/cards/06-picking-list-order/DEV.md` из корня рабочей копии — пройдено.
- `git add night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git commit -m "docs(night): record backend atom 2 rework"` — не выполнено из-за ограничения песочницы: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` (`Operation not permitted`). Сама модель сохранена в коммите `c8f3458b6`, усиление интеграционного теста — в `3dc855d9591ca1f1c4f271304ee63fe42bd62b2c`; незакоммичен только обновлённый `DEV.md`.

## Не реализовано

- Находки 1–4 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/REVIEW.md` относятся к подключению модалки, физической печатной ленте и тестам frontend. Они не относятся к двум backend-файлам и слою атома 2, поэтому в этой переделке не исправлялись.
- Следующие атомы из `FEATURES.md` не выполнялись.

## Блокеры

- Backend-реализация и тест сохранены в Git. Новый отчёт переделки записан в рабочую копию, но его отдельный коммит заблокирован запретом записи в общую мета-папку Git worktree.

## Находки

- `REVIEW.md` отдельно подтверждает корректность серверного ключа с развязкой по `wb_order_id`, затем `order.id`; backend-находок для атома 2 нет.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 3

# Backend Dev · 06-picking-list-order · атом 3 · переделка

## Что реализовано

- Эндпоинт: существующий `GET /operations/fbs-supplies/{supply_id}/picking-list` перепроверен; он возвращает серверные товарные группы, непрерывные диапазоны `number_start` / `number_end` и канонический полный `order_ids`.
- Сервис: существующий `get_picking_list` перепроверен; группы сортируются по `(article, sku_code, size, product_name)`, а заказы внутри группы — по `wb_order_id`, затем `order.id`.
- Тест: API-сценарий усилен проверкой полного развёрнутого `order_ids` и равенства длины диапазона, `quantity` и количества идентификаторов в каждой строке.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — усилен сценарий `test_fbs_supply_picking_list_grouping`: он проверяет полный канонический порядок всех заказов и согласованность каждого диапазона с количеством строки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — записан отчёт переделки атома 3.

Существующая реализация в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py` уже буквально выполняет контракт; переделка после ревью не потребовала изменения этих файлов.

## Миграции

- Нет: схема данных не менялась.

## Тесты

- `test_fbs_supply_picking_list_grouping` — проверяет перемешанную вставку нескольких товарных групп, пустые и совпадающие товарные признаки, одиночные номера и диапазоны, полный канонический `order_ids`, согласованность количества и повторный идентичный ответ API.

## Гейты

- `ruff check /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — пройдено: `All checks passed!`.
- `mypy /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — не пройдено: `21 errors in 5 files`; ошибки находятся в существующих участках `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`, `test_fbs_shipment_warehouse_sc.py` и старых строках `test_fbs_supply_assembly.py`, новое утверждение их не добавляет.
- `pytest -q /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py -k 'test_fbs_supply_picking_list_grouping'` — пройдено: `1 passed, 18 deselected in 5.29s`.
- `python3 scripts/ci/back_guard.py` — не применим: атом не добавляет и не меняет роут.
- `python3 scripts/ci/check_migrations.py` — не применим: атом не добавляет миграцию.
- `git diff --check -- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — пройдено.
- `git add -- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git diff --cached --check && git commit -m "test(fbs): strengthen picking list sequence coverage"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` (`Operation not permitted`).

## Не реализовано

- Находки 1–4 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/REVIEW.md` относятся к подключению модалки, физической печати и frontend-тестам. Они не относятся к backend-файлам и слою атома 3, поэтому в этой переделке не исправлялись.
- Следующие атомы из `FEATURES.md` не выполнялись.

## Блокеры

- Реализация атома, уже существовавшая до переделки, сохранена в истории ветки; текущий `HEAD` — `373ea249`. Усиление теста и новый `DEV.md` локально реализованы, но не сохранены отдельным коммитом: песочница запрещает запись в общую мета-папку Git worktree. Поэтому результат переделки нельзя считать опубликованным или полностью сохранённым в Git.
- Общий типовой gate остаётся красным из-за существующих ошибок вне изменения этого атома; целевой API-сценарий зелёный.

## Находки

- `REVIEW.md` прямо подтверждает корректность серверного листа и ленты; backend-находок для атома 3 нет.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

# Фича 4

# Backend development report · 06-picking-list-order · атом 4 · переделка

## Что реализовано

- Эндпоинт `POST /operations/fbs-supplies/{supply_id}/order-print-tape` — ранее реализованная нормализация полного набора ID по канонической серверной последовательности и выдача постоянного `order_number` проверены без изменения API.
- Сервис `print_fbs_order_tape` — добавлен регрессионный сценарий, доказывающий, что отсутствующий PNG сохраняет номер проблемного заказа, а следующий готовый заказ не сдвигается в освободившийся номер.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — добавлен сервисный тест пропуска WB PNG с постоянными номерами `1, ошибка № 2, 3` при перемешанном запросе.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — отчёт текущей переделки.

## Миграции

Нет.

## Тесты

- `test_fbs_order_tape_missing_png_preserves_following_order_number` — один отсутствующий WB PNG получает постоянный номер `2`, готовые заказы возвращаются с номерами `1` и `3`, порядок входных ID не используется как порядок ленты.
- Существующие `test_fbs_order_tape_*` — полный набор, каноническая сортировка и номер при построчной перепечатке.
- `test_tape_covers_every_order_and_matches_picking_list` — endpoint принимает перемешанный полный состав, возвращает порядок и номера листа `1..N`, повторная печать сохраняет их.

## Гейты

- `ruff check app/services/fbs_order_tape_print_service.py app/api/fbs_supplies.py tests/test_fbs_supply_assembly.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено: `All checks passed!`.
- `mypy app/services/fbs_order_tape_print_service.py app/api/fbs_supplies.py tests/test_fbs_supply_assembly.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — не пройдено: `21 errors in 5 files`; все диагностики существовали до переделки, новый тест новых ошибок не добавил.
- `pytest -q tests/test_fbs_supply_assembly.py -k 'fbs_order_tape'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено: `5 passed, 15 deselected in 0.14s`.
- `pytest -q tests/test_fbs_packaging_integration.py -k 'tape_covers_every_order_and_matches_picking_list'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено: `1 passed, 14 deselected in 2.12s`.
- `python3 scripts/ci/back_guard.py` — не применим: текущая переделка не добавляет и не меняет роут.
- `python3 scripts/ci/check_migrations.py` — не применим: миграций нет.
- `git add -- backend/tests/test_fbs_supply_assembly.py night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git diff --cached --check && git commit -m "test(fbs): preserve tape numbers across sticker gaps"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` (`Operation not permitted`).

## Не реализовано

- Находки 1–4 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/REVIEW.md` относятся к подключению модалки, физическому frontend-рендереру ленты и UI-тестам. Они находятся вне роли `backend-dev` и файлов backend-атома, поэтому не исправлялись.
- Следующие атомы из `FEATURES.md` не выполнялись.

## Находки

- Серверная реализация атома уже присутствовала в истории ветки и в `REVIEW.md` отмечена как корректная; переделка закрывает отсутствовавшее целевое доказательство сценария с ошибкой одного PNG.
- Несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/JOURNAL.md` сохранено без изменений и в коммит атома не включается.

## Блокеры

- Переделка локально реализована и проверена, но новый тест и этот отчёт не сохранены отдельным коммитом: среда запрещает запись в общую метапапку Git worktree. Последний сохранённый `HEAD` — `a62c8de8`; он не содержит текущую переделку.

# Фича 5

# DEV · 06-picking-list-order · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/fbsApi.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.test.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — **красный на существующих зависимостях вне разрешённых файлов атома**. Ошибки: `frontend/src/ui-kit/Cells.tsx:89` использует отсутствующий в MUI 9 prop `inputProps`; `frontend/src/ui-kit/ModalFrame.tsx:32-33` использует отсутствующий prop `disableEscapeKeyDown`, а параметр `reason` не используется. В изменённых файлах TypeScript-ошибок нет.
- `python3 scripts/ui/ui_guard.py` из корня — **красный на существующих файлах вне разрешённых файлов атома**: `frontend/src/components/WbProductPickerDialog.tsx` (`экран-монолит 0 → 646`) и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx` (`экран-монолит 1111 → 1169`). Базовая линия не обновлялась. По затронутым экранам проверка сообщает улучшения: `FfFbsPickList.tsx` — убраны локальные чип, кнопки и таблица; `FfFbsSupplyWorkspace.tsx` — монолит уменьшен.
- `npm run test:unit` из `frontend/` — **зелёный**: 21 файл, 149 тестов пройдены. Добавлены проверки полного серверного набора ID, порядка `WB → WMS № K`, сохранения номера вокруг пропущенного стикера и использования сохранённого изображения Честного знака вместо текстового КИЗ.

## Не реализовано

- Нельзя буквально сдать зелёные `tsc` и `ui_guard.py`, не меняя запрещённые этим атомом соседние файлы. Конкретные внешние ошибки перечислены в разделе «Гейты»; файлы и базовая линия не тронуты.
- Живой браузерный проход не выполнялся: роль `screen-dev` реализует экран и unit-проверки, но не подменяет роль проверки готового результата.
- Commit создать не удалось: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` из-за `Operation not permitted`. Метаданные общего Git-каталога находятся вне разрешённой для записи рабочей копии; изменения остаются локальными и незакоммиченными.

# Фича 6

# DEV · 06-picking-list-order · переделка по REVIEW

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md`

В `ff-fbs-supply.spec.ts` добавлены пользовательские браузерные сценарии, которые открывают лист через видимую кнопку рабочего места, а не изолированный компонент: `S-03-TC-001` проверяет серверный порядок и диапазоны, `S-03-TC-002` — локальную отметку и отсутствие перенумерации после фильтра, `S-03-TC-003` — передачу полного канонического набора заказов при пустом результате фильтра, `S-03-TC-006` — пустую поставку, `S-03-TC-007` — блокировку повторной печати, кнопки закрытия и Escape во время подготовки.

Исправления первых трёх находок ревью уже находятся в текущем сохранённом коммите `e60b085d998a470c986e0ca8614bae11ffde6a9f`: `FfFbsPickList` подключён к `FfFbsSupplyWorkspace`, оба полных маршрута печати используют серверный порядок, предпросмотр строит пару `WB → WMS № K`, а Честный знак берётся из сохранённого изображения или формируется как DataMatrix, но не печатается текстом КИЗ.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `frontend/` — **красный на существующих файлах вне разрешённого слоя атома**. Ошибки: `frontend/src/ui-kit/Cells.tsx:89` — MUI 9 не принимает `inputProps`; `frontend/src/ui-kit/ModalFrame.tsx:32-33` — MUI 9 не принимает `disableEscapeKeyDown`, параметр `reason` не используется. В изменённом e2e-файле ошибок не найдено.
- `python3 scripts/ui/ui_guard.py` из корня — **красный на существующих соседних файлах**: `frontend/src/components/WbProductPickerDialog.tsx` (`экран-монолит 0 → 646`) и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx` (`экран-монолит 1111 → 1169`). Базовая линия не обновлялась. По слою карточки guard сообщает улучшения в `FfFbsPickList.tsx` и `FfFbsSupplyWorkspace.tsx`.
- `npm run test:unit` из `frontend/` — **зелёный**: 21 файл, 149 тестов пройдены.
- `npx eslint tests-e2e/ff-fbs-supply.spec.ts` из `frontend/` — **зелёный**.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-00(1|2|3|6|7)' --list` — **зелёный**: Playwright обнаруживает все 5 сценариев.
- Живой запуск тех же 5 Playwright-сценариев — **заблокирован средой** до выполнения тестов: webServer не может открыть `127.0.0.1:18000`, ошибка `[Errno 1] operation not permitted`.

## Не реализовано

- Буквально зелёные `tsc` и `ui_guard.py` недостижимы без правок файлов вне разрешённой границы этого атома; конкретные внешние ошибки перечислены в разделе «Гейты».
- Живой Playwright-прогон не завершён из-за запрета среды на локальный bind порта. Сценарии добавлены, компилируются, перечисляются Playwright и проходят ESLint, но их браузерный результат в этой среде не заявляется как зелёный.
- Новый e2e-слой и этот отчёт локально реализованы, но не сохранены новым commit: `git add` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` (`Operation not permitted`). Восстановимый HEAD остаётся `e60b085d998a470c986e0ca8614bae11ffde6a9f`; незакоммиченный diff необходимо сохранить оркестратору с доступом на запись к общему Git-каталогу.

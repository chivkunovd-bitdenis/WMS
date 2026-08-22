# Фича 1

# DEV · 06-picking-list-order · атом 1 · переделка по REVIEW

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/ModalFrame.tsx` — убран отсутствующий в установленной MUI 9 prop `disableEscapeKeyDown`; управляемая модалка по-прежнему игнорирует любой запрос закрытия, пока `busy=true`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Cells.tsx` — aria-подпись `CheckCell` передаётся в нативный input через актуальный MUI API `slotProps.input`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/PickingListPrimitives.test.ts` — точечная проверка `ModalFrame` приведена к актуальному публичному контракту компонента и продолжает доказывать блокировку закрытия в состоянии `busy`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — записан отчёт переделки атома.

Остальные разрешённые файлы атома уже содержат требуемые `ChoiceFilter`, `PrintAction` со значением `стикеры заказов`, экспорты и изолированную демонстрацию всех четырёх элементов в `UiKitShowcase`; находка ревью не потребовала их изменения.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **зелёный**, код завершения 0.
- `npm run test:unit -- src/ui-kit/PickingListPrimitives.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **зелёный**, 1 файл и 4 теста пройдены.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — **красный только на двух существующих нарушениях вне файлов атома**: `frontend/src/components/WbProductPickerDialog.tsx` (`экран-монолит 0 → 646`) и `frontend/src/screens/v2/SellerInboundDraftScreen.tsx` (`экран-монолит 1111 → 1169`). Для карточки guard фиксирует улучшения в `FfFbsPickList.tsx` и `FfFbsSupplyWorkspace.tsx`; новых нарушений в UI-kit нет, базовая линия не менялась.
- `git diff --check -- frontend/src/ui-kit/ModalFrame.tsx frontend/src/ui-kit/Cells.tsx frontend/src/ui-kit/PickingListPrimitives.test.ts night/volna-9-recovery/cards/06-picking-list-order/DEV.md` из корня рабочей копии — **зелёный**, код завершения 0.
- `git add -- frontend/src/ui-kit/ModalFrame.tsx frontend/src/ui-kit/Cells.tsx frontend/src/ui-kit/PickingListPrimitives.test.ts night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git diff --cached --check && git commit -m "fix(ui-kit): support MUI 9 picking primitives"` из корня рабочей копии — **красный из-за ограничения среды**: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` (`Operation not permitted`). Несвязанные изменения оркестратора в коммит не добавлялись.

## Не реализовано

- Находки 1, 3–6 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/REVIEW.md` относятся к реестру экрана, продуктовой модалке, backend-сервису, общему предпросмотру печати и браузерным сценариям. Они не относятся к файлам и слою атома 1, поэтому в этой переделке не исправлялись.
- Полностью зелёный `ui_guard.py` нельзя получить в границе атома: оба новых нарушения находятся в запрещённых для этой роли соседних экранах. Храповая базовая линия намеренно не обновлялась.
- Отдельный восстанавливаемый commit SHA не создан: общая Git-метапапка worktree находится вне доступной для записи области. Исправление локально реализовано, но не сохранено в Git.
- Следующие атомы из `FEATURES.md` не выполнялись.

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

# Backend development report · 06-picking-list-order · атом 4 · переделка по REVIEW

## Что реализовано

- Эндпоинт `POST /operations/fbs-supplies/{supply_id}/order-print-tape` — контракт ответа сохранён; для отсутствующего WB PNG возвращается одна конкретная ошибка с постоянным `order_number`, без второго общего `order_qr_missing`.
- Сервис `print_fbs_order_tape` — ошибка из `PrintBatchResult.order_errors` считается уже зарегистрированной ошибкой WB-стикера; отсутствие готового asset больше не дублирует её, а следующий заказ сохраняет исходный номер полного листа.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py` — исключено повторное добавление общей ошибки для заказа, по которому batch уже вернул конкретную ошибку WB-стикера.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — регрессионная проверка усилена до точного требования: у проблемного заказа одна ошибка `wb_sticker_missing` с номером `2`, следующий готовый заказ остаётся номером `3`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — отчёт текущей переделки.

## Миграции

Нет.

## Тесты

- `test_fbs_order_tape_missing_png_preserves_following_order_number` — перемешанный полный набор нормализуется сервером; отсутствующий PNG даёт ровно одну исходную batch-ошибку с постоянным номером `2`; готовые заказы имеют номера `1` и `3`.
- Существующие `test_fbs_order_tape_*` — полный состав, канонический порядок, стабильная нумерация и совместимость построчной перепечатки.
- `test_tape_covers_every_order_and_matches_picking_list` — интеграционный endpoint-сценарий одинакового порядка листа и ленты при перемешанных ID и повторной печати.

## Гейты

- `ruff check app/services/fbs_order_tape_print_service.py app/api/fbs_supplies.py tests/test_fbs_supply_assembly.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено, `All checks passed!`, код 0.
- `mypy app/services/fbs_order_tape_print_service.py app/api/fbs_supplies.py tests/test_fbs_supply_assembly.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — не пройдено: 21 существующая диагностика в 5 файлах, включая транзитивно проверенные `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`, `test_fbs_shipment_warehouse_sc.py` и прежние строки `test_fbs_supply_assembly.py`; изменённые строки новой диагностики не добавили.
- `pytest -q tests/test_fbs_supply_assembly.py -k 'fbs_order_tape'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено: `5 passed, 15 deselected in 0.08s`, код 0.
- `pytest -q tests/test_fbs_packaging_integration.py -k 'tape_covers_every_order_and_matches_picking_list'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено: `1 passed, 14 deselected in 1.08s`, код 0.
- `python3 scripts/ci/back_guard.py` — не применим: атом не добавляет и не меняет роут.
- `python3 scripts/ci/check_migrations.py` — не применим: миграций нет.
- `git diff --check -- backend/app/services/fbs_order_tape_print_service.py backend/tests/test_fbs_supply_assembly.py night/volna-9-recovery/cards/06-picking-list-order/DEV.md` из корня рабочей копии — пройдено, код 0.
- `git add -- backend/app/services/fbs_order_tape_print_service.py backend/tests/test_fbs_supply_assembly.py night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git diff --cached --check && git commit -m "fix(fbs): avoid duplicate tape sticker errors"` из корня рабочей копии — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock`, `Operation not permitted`.

## Не реализовано

- Frontend-часть находки 4 (`FbsPrintPreviewDialog.tsx` показывает одинаковый текст для разных кодов ошибок) не относится к роли `backend-dev` и файлам атома.
- Находки 1–3 и 5–6 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/REVIEW.md` относятся к frontend-реестру, UI-компонентам, маршруту модалки, режимам предпросмотра и браузерным тестам; они не исправлялись.
- Следующие атомы из `FEATURES.md` не выполнялись.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
- Несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/JOURNAL.md` сохранено без изменений и в коммит атома не включается.

## Блокеры

- Реализация и целевые тесты выполнены локально, но отдельный восстанавливаемый коммит создать невозможно: общая Git-метапапка worktree недоступна среде для записи. Последний сохранённый `HEAD` — `e5230651`; он не содержит текущую переделку.
- Узкий `mypy` имеет существующий технический долг, перечисленный в разделе «Гейты»; новых диагностик на изменённых строках нет.

# Фича 5

# DEV · 06-picking-list-order · атом 5 · rework DESIGN-REVIEW

Роль: `screen-dev`.

Исправлены все три находки `DESIGN-REVIEW.md`, относящиеся к слою этого атома: действия в «Листе подбора» объединены через `ActionGroup`, а в предпросмотре закрытие и печать переведены на `SecondaryAction` и `PrintAction`. Логика серверного порядка, полного набора ID и пар `WB → WMS № K` не изменялась.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/tests-e2e/ff-fbs-supply.spec.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md`

## Гейты

- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npx tsc --noEmit -p tsconfig.app.json` (exit 0).
- Красный вне границы атома — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order && python3 scripts/ui/ui_guard.py` (exit 1). Новые нарушения: `src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646` и `src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169`. Оба файла не входят в разрешённую границу экрана и уже перечислены в `DESIGN-REVIEW.md`; baseline не обновлялся. Для файлов атома guard сообщил только улучшения: у `FbsPrintPreviewDialog.tsx` число собственных кнопок уменьшилось `4 → 2`, у `FfFbsPickList.tsx` собственные кнопки уменьшились `2 → 0`.
- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npm run test:unit -- src/screens/v2/FbsPrintPreviewDialog.test.ts src/screens/v2/FfFbsPickList.test.ts` (2 файла, 11 тестов, exit 0).
- Не стартовал из-за ограничения среды — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-004 S-03-TC-005'`. WebServer получил `operation not permitted` при попытке слушать `127.0.0.1:18000`; продуктовый сценарий до браузера не дошёл.
- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order && git diff --check` (exit 0).
- Не выполнено из-за прав файловой системы — `git add frontend/src/screens/v2/FfFbsPickList.tsx frontend/src/screens/v2/FbsPrintPreviewDialog.tsx frontend/tests-e2e/ff-fbs-supply.spec.ts night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git commit -m "fix(fbs): align picking print actions with ui kit"`. Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock`: `Operation not permitted`. Commit SHA отсутствует.

## Не реализовано

Все три находки `DESIGN-REVIEW.md` реализованы буквально. Непроверенным остался браузерный прогон `S-03-TC-004/S-03-TC-005`: локальный webServer запрещён средой выполнения. Два чужих нарушения `ui_guard.py` не исправлялись, потому что их файлы находятся вне границы этого атома и роли `screen-dev`. Изменения локально записаны, но не сохранены Git-коммитом из-за запрета записи в metadata-каталог worktree.

## Находки

Новых находок по данным, персональным данным или секретам нет.

# Фича 6

# DEV · 06-picking-list-order · атом 6 · rework DESIGN-REVIEW

Роль: `screen-dev`.

Все три находки `DESIGN-REVIEW.md` в текущей ветке реализованы буквально и сохранены в коммите `b6d7142dc2f86b5bf813a1b5b58cbe79edcd600b`: действия листа подбора объединены через `ActionGroup`, а в предпросмотре ленты закрытие и печать переведены на `SecondaryAction` и `PrintAction` с типом `стикеры заказов`. Канонические диапазоны, локальные отметки и полный состав печати не изменялись.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx` — исправление R-32 находится в проверенном коммите `b6d7142dc2f86b5bf813a1b5b58cbe79edcd600b`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx` — исправления R-31 и R-33 находятся в проверенном коммите `b6d7142dc2f86b5bf813a1b5b58cbe79edcd600b`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/tests-e2e/ff-fbs-supply.spec.ts` — целевые сценарии атома и связанная проверка действия печати находятся в том же коммите.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — создан заново для текущего прохода атома 6.

## Гейты

- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npx tsc --noEmit -p tsconfig.app.json` (exit 0).
- Красный только вне границы атома — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order && python3 scripts/ui/ui_guard.py` (exit 1). Guard сообщил `src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646` и `src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169`; оба файла не входят в `files` экрана `S-03` и прямо отмечены в `DESIGN-REVIEW.md` как нарушения вне карточки. Baseline не обновлялся. Для файлов атома guard сообщил только улучшения: `FbsPrintPreviewDialog.tsx` — собственные кнопки `4 → 2`; `FfFbsPickList.tsx` — собственный чип `1 → 0`, собственные кнопки `2 → 0`, собственная таблица `1 → 0`.
- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npm run test:unit -- src/screens/v2/FfFbsPickList.test.ts` (1 файл, 5 тестов, exit 0).
- Зелёный — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npm run test:unit -- src/screens/v2/FbsPrintPreviewDialog.test.ts src/screens/v2/FfFbsPickList.test.ts` (2 файла, 11 тестов, exit 0).
- Не стартовал из-за ограничения среды — `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend && npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-00(1|2|3|6|7)'`. Playwright webServer получил `[Errno 1] operation not permitted` при попытке слушать `127.0.0.1:18000`; сценарии до браузера не дошли, тестовых падений не зафиксировано.

## Не реализовано

Пунктов контракта или находок `DESIGN-REVIEW.md`, которые не удалось реализовать буквально, нет. Непроверенными в браузере остались `S-03-TC-001`, `S-03-TC-002`, `S-03-TC-003`, `S-03-TC-006` и `S-03-TC-007`, потому что песочница запретила запуск локального webServer. Два чужих нарушения `ui_guard.py` не исправлялись: их файлы находятся вне границы экрана `S-03` и роли `screen-dev`.

## Находки

Новых находок по данным, персональным данным или секретам нет.

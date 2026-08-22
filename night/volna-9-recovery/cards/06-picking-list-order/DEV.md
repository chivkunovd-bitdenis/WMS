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

# Screen development report · 06-picking-list-order · атом 5 · переделка по REVIEW

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/fbsApi.ts` — добавлено безопасное отображение кодов ошибок полной ленты на языке склада: только отсутствие PNG называется неполученным стикером.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — печать из открытого листа использует полный серверный снимок `order_ids`, показанный оператору, и превращает конфликт изменившегося состава в требование обновить лист.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx` — полный маршрут показывает ошибки в постоянном порядке, скрывает выборочную печать и поле копий, а физическая лента всегда содержит ровно одну пару `WB → WMS № K` на готовый заказ.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx` — прямо названный ревьюером файл того же слоя передаёт в запуск печати полный снимок ID уже загруженного листа и не загружает второй снимок молча.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.test.ts` — добавлена проверка разных складских формулировок для отсутствующего WB-стикера, отсутствующей строки упаковки и ошибки передачи маркировки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/tests-e2e/ff-fbs-supply.spec.ts` — добавлены сценарии `S-03-TC-004`, `S-03-TC-005` и `S-03-TC-008`: итоговая кнопка, содержимое открытого окна печати, повторная полная лента, запрет копий/выборочной печати, разные `ErrorNotice` и отказ печатать устаревший лист.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — этот отчёт.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **зелёный**, код 0; финальный прогон выполнен после продуктовых правок.
- `npm run test:unit -- src/screens/v2/FbsPrintPreviewDialog.test.ts src/screens/v2/FfFbsPickList.test.ts src/screens/v2/FfFbsSupplyWorkspace.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **зелёный**, 3 файла и 14 тестов прошли; финальный прогон выполнен после продуктовых правок.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — **красный вне границ атома**: baseline сообщает новые нарушения `src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646` и `src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169`. Эти файлы не менялись. Для `FfFbsPickList.tsx` guard сообщает улучшения: `свой-чип 1 → 0`, `своя-кнопка 2 → 0`, `своя-таблица 1 → 0`; для `FfFbsSupplyWorkspace.tsx` — `экран-монолит 2493 → 2451`. Baseline не обновлялась.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-003|S-03-TC-004 S-03-TC-005|S-03-TC-008'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **красный по среде до запуска кейсов**: Playwright webServer не смог открыть `127.0.0.1:18000`, `[Errno 1] operation not permitted`; тесты не исполнялись.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-003|S-03-TC-004|S-03-TC-005|S-03-TC-008' --list` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **зелёный**, обнаружены 4 целевых сценария в одном файле, включая отдельный сценарий ошибок предпросмотра.
- `npx eslint src/screens/v2/FfFbsPickList.tsx src/screens/v2/FfFbsSupplyWorkspace.tsx src/screens/v2/FbsPrintPreviewDialog.tsx src/screens/v2/fbsApi.ts src/screens/v2/FbsPrintPreviewDialog.test.ts tests-e2e/ff-fbs-supply.spec.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **красный на существующей структуре файлов**: 5 правил `react-refresh/only-export-components` для ранее экспортированных чистых функций в `FbsPrintPreviewDialog.tsx` и `FfFbsPickList.tsx`; новых иных диагностик нет.
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — **зелёный**, код 0 до записи отчёта.
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` после записи отчёта — **зелёный**, код 0.
- `git add -- frontend/src/screens/v2/fbsApi.ts frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx frontend/src/screens/v2/FbsPrintPreviewDialog.tsx frontend/src/screens/v2/FfFbsPickList.tsx frontend/src/screens/v2/FbsPrintPreviewDialog.test.ts frontend/tests-e2e/ff-fbs-supply.spec.ts night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m "fix(fbs): keep picking list tape consistent"` — **не выполнено средой**: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock`, `Operation not permitted`. Текущий сохранённый `HEAD` — `a21180bfadacdf0eb8464550a625aa48a3049e77`; он не содержит эту переделку.

## Не реализовано

- Пункты контракта атома 5 реализованы буквально; функциональных пропусков внутри разрешённого слоя нет.
- Находка 1 ревью про регистрацию `FfFbsPickList.tsx` относится к границе атома 6 и `frontend/screens.registry.json`; этот атом реестр не меняет.
- Находка 2 ревью про несовместимые свойства MUI относится к примитивам атома 1 в `frontend/src/ui-kit/`; этот атом их не меняет.
- Живой браузерный результат четырёх сценариев не подтверждён из-за запрета sandbox на локальный порт; это ограничение проверки, а не пропущенная ветка реализации.
- Отдельный Git-коммит атома не создан из-за read-only доступа sandbox к общей Git-метапапке worktree. Изменения находятся в постоянной назначенной рабочей копии, но пока не являются восстанавливаемым Git-результатом.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
- Несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/JOURNAL.md` сохранено без изменений и в коммит атома не включается.

# Фича 6

# Screen development report · 06-picking-list-order · атом 6 · переделка по REVIEW

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/screens.registry.json` — `FfFbsPickList.tsx` зарегистрирован в `files` экрана `S-03`, поэтому модалка теперь входит в разрешённую границу экранного конвейера; это исправляет находку 1 ревью.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — записан обязательный отчёт текущего атома.

Остальные находки ревью уже исправлены предыдущими атомарными коммитами этой же ветки: совместимость MUI — `e5230651`, устранение дубля ошибки WB — `a21180bf`, согласованность снимка листа и ленты, запрет выборочной печати/копий и браузерные регрессии — `4e98a155`.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **зелёный**, код 0.
- `npm run test:unit -- src/ui-kit/PickingListPrimitives.test.ts src/screens/v2/FfFbsPickList.test.ts src/screens/v2/FbsPrintPreviewDialog.test.ts src/screens/v2/FfFbsSupplyWorkspace.test.ts` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **зелёный**, прошли 4 файла и 18 тестов.
- `python3 scripts/ui/ui_guard.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — **красный только вне границ атома**: существующие нарушения `src/components/WbProductPickerDialog.tsx: экран-монолит 0 → 646` и `src/screens/v2/SellerInboundDraftScreen.tsx: экран-монолит 1111 → 1169`. Для файлов карточки новых нарушений нет; guard отмечает улучшения `FfFbsPickList.tsx` по собственной таблице, кнопкам и чипам и `FfFbsSupplyWorkspace.tsx` по размеру монолита. Baseline не обновлялась.
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-00[1-8]'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **красный по ограничению среды до запуска кейсов**: Playwright API дошёл до старта, но sandbox запретил bind `127.0.0.1:18000` (`operation not permitted`).
- `npx playwright test tests-e2e/ff-fbs-supply.spec.ts --grep 'S-03-TC-00[1-8]' --list` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend` — **зелёный**: найдены 8 целевых тестов в одном файле, включая `S-03-TC-001`, `S-03-TC-002`, `S-03-TC-003`, `S-03-TC-004`, `S-03-TC-005`, `S-03-TC-006`, `S-03-TC-007`, `S-03-TC-008`.
- `python3 -m json.tool frontend/screens.registry.json >/dev/null` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — **зелёный**, реестр остаётся валидным JSON.
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — **зелёный**, код 0 до записи отчёта.
- `git add -- frontend/screens.registry.json night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m 'fix(fbs): register picking list screen'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — **красный по ограничению среды**: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock`, `Operation not permitted`; индекс не изменён, коммит не создан.

## Не реализовано

- Пункты контракта и все шесть находок ревью в коде ветки закрыты; буквальных пропусков в разрешённом слое нет.
- Живое выполнение Playwright-сценариев не подтверждено из-за запрета sandbox на локальный порт. Проверено только обнаружение всех восьми целевых сценариев; это ограничение проверки, а не замена browser product review.
- Изменение реестра и этот отчёт находятся в постоянной рабочей копии, но не сохранены отдельным Git-коммитом из-за read-only доступа к общей Git-метапапке. Последний сохранённый `HEAD` — `4e98a155db61`; он содержит исправления находок 2–6, но не текущую регистрацию экрана из находки 1.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
- Несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/JOURNAL.md` сохранено без изменений и в коммит атома не включается.

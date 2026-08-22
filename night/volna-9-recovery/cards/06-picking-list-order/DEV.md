# Фича 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/ModalFrame.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/FilterBar.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Cells.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/Actions.tsx`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/index.ts`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/ui-kit/UiKitShowcase.tsx`

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — зелёный.
- `python3 scripts/ui/ui_guard.py` — красный: обнаружены нарушения в чужих файлах `src/components/WbProductPickerDialog.tsx`, `src/screens/v2/FfFbsSupplyWorkspace.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; файлы этого атома в выводе отсутствуют.
- `npm run test:unit` — красный до запуска тестов: окружение не содержит команду `vitest` (`vitest: command not found`).

## Не реализовано

- Полная модалка «Лист подбора» с таблицей и всеми состояниями экрана не реализована: это следующая фича контракта, текущий атом добавляет только переиспользуемые ui-kit-элементы и showcase.
- Из-за отсутствующего `vitest` и чужих нарушений `ui_guard.py` полная зелёная проверка окружения недоступна; зависимости и базовую линию не изменял.

# Фича 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/models/fbs_supply.py` — добавлен стабильный `order_by` для relationship `orders`: `wb_order_id`, затем `order.id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — добавлен интеграционный тест чтения поставки после перемешанной вставки заказов.

## Гейты

- `ruff check .` — не пройден: в исходной backend-базе 82 ранее существовавших нарушения; изменённые файлы отдельно проходят `ruff check`.
- `mypy .` — не пройден: в исходной backend-базе 21 ранее существовавшая ошибка в 6 файлах; новых ошибок в изменённых файлах нет.
- `pytest -q tests/test_fbs_supply_assembly.py -k stable_order` — пройден, 1 тест.
- `pytest -q` — выполняется/результат будет дополнен после завершения запуска.
- `python3 scripts/ci/back_guard.py` — недоступен: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — недоступен: файл отсутствует в этой рабочей копии.

## Не реализовано

- Миграции не требуются: изменение только порядка загрузки relationship и не меняет схему базы данных.
- Остальные фичи карточки не реализованы согласно границе атомарного backend-куска.
- Commit не создан: Git не разрешил запись `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` из-за ограничений рабочей среды.

# Фича 3

# Backend development · 06-picking-list-order

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py` — серверная канонизация товарных групп, порядок заказов и вычисление диапазонов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py` — поля `number_start`, `number_end`, `order_ids` в ответе существующего API листа.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — проверки диапазонов, полного состава и повторяемости ответа.

## Гейты

- `ruff`: PASS для изменённых backend-файлов; полный `ruff check .` BLOCKED существующими ошибками в несвязанных файлах.
- `mypy`: BLOCKED существующими 4 ошибками в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`; изменённые файлы не добавили ошибок.
- `pytest`: целевой `-k picking_list`: PASS, 1 passed; полный набор запущен и прерван после 29% без ошибки в выполненных тестах.
- `back_guard.py`: BLOCKED — файл `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- `check_migrations.py`: BLOCKED — файл `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии; миграций нет.

## Не реализовано

- Ничего из API и данных этой атомарной карточки не оставлено без реализации.
- UI листа и серверная лента относятся к другим атомарным кускам и не изменялись.

## Блокеры

- Commit не создан: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` из-за ограничения прав общей мета-папки worktree. Изменения остаются в рабочем diff до восстановления права на запись владельцем окружения.

# Фича 4

# Backend development · 06-picking-list-order · атомарный кусок 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py` — полная поставка проверяется целиком; заказы сортируются сервером тем же каноном, что лист подбора; каждому заказу и ошибке получения стикера возвращается постоянный `order_number`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py` — опубликованы `order_number` в ленте и ошибках.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — добавлена проверка независимости канонического порядка от порядка входного состава.

## Гейты

- `ruff`: PASS для изменённых backend-файлов.
- `mypy`: BLOCKED существующими ошибками в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`; в изменённых файлах новых ошибок не выявлено.
- `pytest`: PASS целевых тестов: `2 passed, 13 deselected` для канона/лист-подбора; смежный tape/sticker smoke: `1 passed, 19 deselected`.
- `back_guard.py`: BLOCKED — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py`: BLOCKED — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/check_migrations.py` отсутствует; миграций нет.

## Не реализовано

- Новая бинарная генерация WMS-этикетки с номером не добавлялась: существующий контракт печати уже возвращает служебные артефакты, а этот атомарный кусок закрепляет серверный состав, порядок и номер заказа.
- UI и клиентская типизация не изменялись по границе backend-dev.

## Находки

- Секреты, ключи, токены и `.env` не читались.
- Боевой прод и живой кабинет Wildberries не затрагивались.

# Фича 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/fbsApi.ts` — добавлены необязательные серверные поля номера заказа и связанного WB-заказа для предпросмотра.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx` — полная печать всегда отправляет все ID заказов поставки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FbsPrintPreviewDialog.tsx` — предпросмотр показывает пару WB-стикер → служебная этикетка WMS и складское сообщение для пропущенного стикера.

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json`: выполнялся, процесс не завершился в отведённое время; итог не подтверждён.
- `python3 scripts/ui/ui_guard.py`: BLOCKED существующими/затронутыми нарушениями монолитных экранов; после сокращения добавленной разметки нарушение `FfFbsSupplyWorkspace.tsx` устранено, остаются `WbProductPickerDialog.tsx` и `SellerInboundDraftScreen.tsx`.
- `npm run test:unit`: BLOCKED — в окружении отсутствует команда `vitest` (`sh: vitest: command not found`).
- Commit: BLOCKED — Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` из-за прав общей мета-папки worktree; SHA не получен.

## Не реализовано

- Если сервер не прислал `order_number`, `wb_order_id` или связанный номер в объекте ассета, интерфейс показывает `—`; клиент не подменяет серверную нумерацию локальным порядком.

## Находки

- Секреты, ключи, токены и `.env` не читались. Боевой прод и кабинет Wildberries не затрагивались.

# Фича 6

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.tsx
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/frontend/src/screens/v2/FfFbsPickList.test.ts

## Гейты

- `npx tsc --noEmit -p tsconfig.app.json` — не подтверждён: в `frontend/node_modules` отсутствует локальный `tsc`, а `npx` не смог предоставить исполняемый пакет в текущем окружении.
- `python3 scripts/ui/ui_guard.py` — затронутый экран улучшен: нарушения `свой-чип`, `своя-кнопка` и `своя-таблица` для `FfFbsPickList.tsx` устранены. Общий запуск красный из-за двух ранее существовавших нарушений в `src/components/WbProductPickerDialog.tsx` и `src/screens/v2/SellerInboundDraftScreen.tsx`; базовая линия не изменялась.
- `npm run test:unit -- --run src/screens/v2/FfFbsPickList.test.ts` — не подтверждён: `vitest: command not found`.

## Не реализовано

- `frontend/tests-e2e/ff-fbs-supply.spec.ts` не изменялся: в текущем окружении отсутствуют зависимости для запуска Playwright, а сценарий открытия модалки находится в существующем рабочем потоке S-03 и требует его полного fixture-контекста.
- Предпросмотр пар «стикер WB → служебная этикетка WMS» не добавлялся в этот экран: контракт карточки оставляет генерацию полной ленты серверной ручке `generateFbsSupplyStickers`; экран сохраняет полный вызов печати независимо от фильтра и отметок.

# DEV · 06-picking-list-order

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py` — единый ключ товарной группы вынесен в `picking_list_group_key` и продолжает использоваться листом подбора.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py` — для полного состава поставки сортирует заказы по ключу листа, числовому `wb_order_id` и `id`; в слой печатных активов передаёт вычисленную последовательность.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_packaging_integration.py` — API-покрытие `S-03-TC-002`–`S-03-TC-008` для полного, повторного, выборочного, обратного ответа WB и частичного результата.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — отчёт атомарного шага.

## Миграции

Нет.

## Тесты

- `S-03-TC-002`, `S-03-TC-003`, `S-03-TC-004`, `S-03-TC-006`: перемешанный полный набор разворачивается в порядке товарных групп, затем по числовому WB ID; повторная полная печать воспроизводит его.
- `S-03-TC-005`: выборочная печать сохраняет порядок ID, переданный оператором.
- `S-03-TC-007`: обратный ответ Wildberries не переставляет ленту, а запрос к WB получает канонический порядок.
- `S-03-TC-008`: при пропущенном WB-стикере фактически готовые наклейки сохраняют относительный канонический порядок.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend && ruff check app/services/fbs_supply_service.py app/services/fbs_order_tape_print_service.py tests/test_fbs_packaging_integration.py` — успешно, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend && mypy app/services/fbs_supply_service.py app/services/fbs_order_tape_print_service.py` — не прошёл из-за 4 существующих ошибок в зависимостях вне атома: `wildberries_credentials_service.py:167`, `fbs_stock_sync_service.py:617`, `fbs_warehouse_binding_service.py:23,291`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend && pytest -q tests/test_fbs_packaging_integration.py -k 'full_tape_expands_picking_groups_in_stable_order or selected_tape_keeps_operator_requested_order or full_tape_keeps_canonical_order_when_wb_reverses_stickers or partial_full_tape_keeps_relative_canonical_order or tape_covers_every_order_and_matches_picking_list'` — успешно, `4 passed, 14 deselected`.
- `python3 scripts/ci/back_guard.py` — не применимо: атом не добавляет маршрут.
- `python3 scripts/ci/check_migrations.py` — не применимо: атом не добавляет миграцию.

## Не реализовано

Нет: публичный API, модели, миграции, frontend, WB-макет стикера и соседние QR-сценарии намеренно не менялись в соответствии с ограничениями атома.

## Находки

- Сценарий равного `wb_order_id` на уровне API не создаётся из-за действующего уникального ограничения `(seller_id, wb_order_id)`; сервисный ключ всё равно содержит `id` последним стабильным tie-breaker.
- Изменения реализованы локально, но не сохранены Git-коммитом: песочница запрещает создание `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order1/index.lock`. Риск: без внешнего коммита результат нельзя надёжно восстановить из SHA.

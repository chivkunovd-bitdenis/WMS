# DEV · 06-picking-list-order · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py` — полная лента использует общий безопасный ключ порядка; выборочная и строковая печать не менялись.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py` — ключ групп листа подбора нормализует `None` только для сравнения, сохраняя исходные значения в ответе; общий ключ добавляет числовой `wb_order_id` и `id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_packaging_integration.py` — добавлены проверки смешанного отсутствующего/строкового размера, групп, числового `8 → 12 → 100`, привязки различимых PNG к `orderId` и относительного порядка при неполном ответе WB.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — отчёт этого атома.

## Миграции

Нет.

## Гейты

- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` — пройден.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend && ruff check app/services/fbs_order_tape_print_service.py app/services/fbs_supply_service.py tests/test_fbs_packaging_integration.py` — пройден, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend && mypy app/services/fbs_order_tape_print_service.py app/services/fbs_supply_service.py` — в изменённых модулях ошибок нет, но команда завершилась с четырьмя уже существующими ошибками зависимостей вне атома: `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23,291`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend && pytest tests/test_fbs_packaging_integration.py` — пройдено, `19 passed in 25.36s`.
- `python3 scripts/ci/back_guard.py` и `python3 scripts/ci/check_migrations.py` не запускались: этот атом не добавляет route или миграцию.

## Находки

- В рабочем дереве до атома уже были несвязанные изменения и удалённые артефакты; они не изменялись.

## Не реализовано

- Существующий partial-путь `wb_stickers_incomplete` / `order_qr_missing`, включая число и тексты его ошибок, не менялся: это явно сохранённое поведение данного атома, а не результат новой сортировки.
- Замечание ревью о расхождении frontend-предпросмотра и ленты не менялось: фронтенд не входит в allowlist атома и его переделка запрещена текущим scope-контрактом.

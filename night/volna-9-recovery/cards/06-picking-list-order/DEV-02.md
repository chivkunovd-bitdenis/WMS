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

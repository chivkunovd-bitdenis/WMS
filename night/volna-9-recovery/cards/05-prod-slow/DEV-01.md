# Backend-dev отчёт · 05-prod-slow

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wb_marketplace_orders_service.py` — добавлены независимые `sync_new_orders_for_seller` и `reconcile_orders_for_seller`; старый `sync_seller_orders` оставлен совместимым алиасом лёгкого импорта. Контур `new` больше не вызывает полный постраничный список, а `reconcile` коммитит страницы и делает rollback при ошибке, не возвращая успешный результат незавершённого прохода.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py` — добавлены unit-тесты раздельных контуров, курсоров и ошибки страницы.

## Миграции

Нет.

## Тесты

- `test_new_sync_does_not_fetch_paginated_orders` — `new` вызывает только `/orders/new` и выполняет upsert.
- `test_reconcile_walks_cursor_and_fails_incomplete_pass` — `reconcile` проходит курсоры до пустой страницы и при ошибке следующей страницы откатывается без успешного результата.

## Гейты

- `ruff` — изменённые файлы: PASS (`ruff check app/services/wb_marketplace_orders_service.py tests/test_wb_marketplace_orders_service.py`); полный backend-гейт заблокирован 84 предсуществующими ошибками вне карточки.
- `mypy` — BLOCKED: 4 предсуществующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`; ошибок в изменённом сервисе не выявлено до этих ошибок.
- `pytest` — PASS: `8 passed` для `backend/tests/test_wb_marketplace_orders_service.py`.
- `back_guard.py` — NOT RUN: файл отсутствует в этой рабочей копии (`scripts/ci/back_guard.py` не найден).
- `check_migrations.py` — NOT RUN: файл отсутствует в этой рабочей копии (`scripts/ci/check_migrations.py` не найден).

## Не реализовано

- Планировщики Beat и single-flight не входят в этот атомарный кусок по `FEATURES.md`; не изменялись.
- Статусная сверка и связывание поставок намеренно не запускаются из частого `new`-контура, чтобы он не превращался в полный обход.

## Находки

- В рабочем дереве уже были несвязанные изменения `tests/cases/S-03.md`, `tests/cases/S-04.md` и артефакты `night/`; они не изменялись и не включаются в backend-правку.

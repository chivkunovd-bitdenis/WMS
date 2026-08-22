# Backend-dev отчёт · 05-prod-slow

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wb_marketplace_orders_service.py` — разделены контуры `new` и `reconcile`; `new` читает только текущие задания WB, `reconcile` проходит курсоры до конца и не завершает неполный проход успешно.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py` — добавлены проверки отсутствия полного списка в `new`, полного прохода курсоров, идемпотентного upsert и rollback при ошибке страницы.

## Миграции

Нет.

## Тесты

- `test_new_sync_does_not_fetch_paginated_orders` — `new` не вызывает постраничный полный список и выполняет upsert.
- `test_reconcile_walks_cursor_and_fails_incomplete_pass` — `reconcile` доходит до конца курсоров и при ошибке страницы откатывает незавершённый проход.

## Гейты

- `ruff` — PASS для измененных backend-файлов.
- `mypy` — BLOCKED: 5 ошибок, из них 4 предсуществующие в соседних сервисах и 1 в незакоммиченном соседнем `fbs_autopoll_service.py`; в сервисе этой карточки ошибок нет.
- `pytest` — PASS: 10 тестов `backend/tests/test_wb_marketplace_orders_service.py`.
- `back_guard.py` — NOT RUN: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/scripts/ci/back_guard.py` отсутствует.
- `check_migrations.py` — NOT RUN: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Планировщики, single-flight и UI не входят в этот атомарный backend-кусок и не изменялись.

## Находки

- В рабочем дереве есть несвязанные незакоммиченные изменения планировщика, фоновых задач и журнала; они не включены в этот отчёт как часть атомарного куска.

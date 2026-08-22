# Backend Dev — 03-no-distribution-mode

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/models/fbs_supply.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/alembic/versions/20260821_0094_fbs_supplies_boxes_without_distribution.py

Добавлены сохраняемые поля `boxes_without_distribution_at` и `boxes_without_distribution_by_user_id` на `FbsSupply`; миграция добавляет nullable-колонки и внешний ключ на `users` с `SET NULL`.

## Гейты

- ruff: PASS для изменённых backend-файлов; полный `ruff check .` — FAIL из-за 82 существующих ошибок вне этого изменения.
- mypy: PASS.
- pytest: PASS.
- back_guard.py: NOT RUN — файл отсутствует в этой рабочей копии.
- check_migrations.py: NOT RUN — файл отсутствует в этой рабочей копии.
- `git diff --check`: PASS.
- commit: BLOCKED — Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-03-no-distribution-mode1/index.lock` из-за ограничений записи sandbox.

## Не реализовано

- Переключение режима в сервисе, чтение legacy-ключа коробов, API и workspace относятся к следующим атомарным фичам из FEATURES.md и намеренно не изменялись.

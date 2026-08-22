# 09-A backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/models/billing.py` — частичные уникальные индексы для общих/селлерских версий тарифов и для `reversal_of_id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/alembic/versions/20260822_0094_billing_financial_core.py` — соответствующие добавляющие ограничения миграции.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_models.py` — проверки индексов SQLite-схемы.

## Гейты

- `ruff check .` — FAIL на существующих ошибках вне атома (83 ошибки в других файлах); `ruff check app/models/billing.py tests/test_billing_models.py` — PASS.
- `mypy .` — FAIL на 17 существующих ошибках вне атома; `mypy app/models/billing.py` — PASS.
- `pytest` — прерван после 216 PASS и 3 skipped из 825 тестов, без падений в пройденной части; целевые billing-тесты PASS, 4 теста.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии по указанному пути.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии по указанному пути.
- `git diff --check` — PASS.

## Не реализовано

- Находки ревью про API, сервисы, задачи и frontend не входят в атом 09-A и намеренно не изменялись.
- Отдельная миграция для удаления старой уникальности не нужна: исходная миграция ещё содержит создаваемую схему, поэтому nullable-уникальность заменена до создания таблицы.

## Находки

- В рабочем дереве до начала работы уже были изменены `night/volna-9-recovery/JOURNAL.md` и удалён прежний `night/volna-9-recovery/cards/09-billing/DEV.md`; эти изменения не относятся к коду атома.

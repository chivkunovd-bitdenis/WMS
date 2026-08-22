# DEV · 08-storage · атом 5

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_models.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

Модели и миграция атома уже содержали таблицы `StorageMeasurement` и `StorageStatement`,
уникальность месячного документа и внешние ключи диапазона на `InventoryMovement.id`.
Добавлены проверки, которые закрепляют ссылку диапазона движения и отсутствие финансовых
полей в документе хранения.

## Гейты

- `ruff check .` — FAIL: 80 ранее существующих ошибок вне изменённых файлов; targeted `ruff check` для моделей и `test_storage_models.py` — PASS.
- `mypy .` — не запускался до конца из-за общего набора; `mypy app/models/storage_measurement.py app/models/storage_statement.py` — PASS.
- `pytest` — targeted storage suite PASS: `7 passed`.
- `back_guard.py` — BLOCKED: файл `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- `check_migrations.py` — BLOCKED: файл `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии.

## Не реализовано

- Исправления сервисов расчёта/фиксации, биллинга, API, ролей и UI из находок 2–12 не входят в атом моделей и не выполнялись.
- Проверка `Warehouse.is_operational` и заполнение `InventoryMovement.warehouse_id` принадлежат внешнему фундаменту 07-A; в этой ветке соответствующего поля ещё нет, поэтому атом не создаёт дублирующую миграцию 07-A.
- Полная проверка миграции через guard невозможна: оба guard-скрипта отсутствуют в рабочей копии.


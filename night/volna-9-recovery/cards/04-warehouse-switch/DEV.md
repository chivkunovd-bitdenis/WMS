# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/catalog_service.py` — создание, генерация из стеллажа и переименование ячейки теперь отвергают совпадение с кодом или штрихкодом склада того же tenant.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_warehouses.py` — добавлены проверки конфликтов при создании и переименовании ячейки; сохранена проверка типов warehouse/location.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — этот отчёт.

## Гейты

- `ruff check .` — FAIL: 80 ранее существовавших ошибок в несвязанных файлах backend/scripts; изменённые файлы в выводе не фигурируют.
- `mypy .` — FAIL: 21 ранее существовавшая ошибка в 6 несвязанных файлах; изменённые файлы не фигурируют.
- `pytest tests/test_warehouses.py` — PASS: 1 passed.
- `pytest` — FAIL/остановлен после 50 passed: существующий `tests/test_document_number_service.py::test_inbound_and_unload_api_assign_document_number` падает с `ValueError: product seller not found`, затем полный прогон был прерван из-за длительного зависания.
- `python3 scripts/ci/back_guard.py` — NOT RUN: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — NOT RUN: файл отсутствует в этой рабочей копии.

## Не реализовано

- Новая миграция не добавлялась: `backend/alembic/versions/20260822_0094_warehouse_operational_barcode.py` уже присутствует в рабочей копии и покрывает `is_operational`, `barcode` и legacy `fbs-wb-*` / `FBS WB *` backfill.
- UI- и соседние backend-находки из ревью не входят в этот атом и не изменялись.

## Находки

- Полный backend-гейт блокирован несвязанными ошибками базовой ветки, перечисленными выше.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py` — добавлен сценарий batch-сверки 201 активного заказа: последовательные пачки 100/100/1, ответ в обратном порядке, частичный ответ, ошибка средней пачки и продолжение последней.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт backend-разработки.

## Гейты

- `ruff check .` из `backend/` — не пройден: 82 существующие ошибки в несвязанных файлах; добавленный `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py` проходит `ruff check`.
- `mypy .` из `backend/` — не пройден: 21 существующая ошибка в шести несвязанных файлах (`inventory_movement_report_service.py`, `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`, `wildberries_product_import_service.py`, служебный cleanup-скрипт).
- `pytest` из `backend/` — полный запуск стартовал (839 тестов), но среда оборвала поток до итогового кода; целевой `pytest tests/test_fbs_marking.py -q` пройден: 6 passed.
- `python3 scripts/ci/back_guard.py` из корня — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` в этой рабочей копии нет.
- `python3 scripts/ci/check_migrations.py` из корня — не запущен по той же причине: каталога `scripts/ci/` в этой рабочей копии нет.
- `git diff --check` — пройден.

## Не реализовано

- Изменений сервисов не потребовалось: текущая реализация `sync_marking_statuses_for_assembling_supplies` уже последовательно режет уникальные `wb_order_id` на пачки до 100, пропускает локальную обработку отсутствующих строк частичного ответа и продолжает после ошибки пачки. Добавлен регрессионный тест, который закрепляет эти требования и находку ревью №3.

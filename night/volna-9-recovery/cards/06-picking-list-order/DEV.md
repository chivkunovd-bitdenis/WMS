# DEV · 06-picking-list-order · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — усилен реальный API-тест `GET /operations/fbs-supplies/{supply_id}/picking-list`: поставка собирается в перемешанном порядке, проверяются канонические товарные группы, полный `order_ids`, непрерывные диапазоны и повторяемость ответа.

## Гейты

- `ruff check .` — FAIL: 83 существующие ошибки backend; одна ошибка в изменённом тесте исправлена, после этого целевой тестовый файл без новых замечаний.
- `mypy .` — FAIL: 21 существующая ошибка в 6 других файлах; изменённые файлы в выводе отсутствуют.
- `pytest -q tests/test_fbs_supply_assembly.py` — PASS: 15 passed, 1 skipped.
- `pytest -q` — RUNNING при формировании артефакта; целевой набор прошёл.
- `python3 scripts/ci/back_guard.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Находки ревью про `order-print-tape` относятся к атомам 4–6 и не изменялись в рамках атомарного backend-куска 3.
- Миграции не нужны: изменены только тесты, схема базы не менялась.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

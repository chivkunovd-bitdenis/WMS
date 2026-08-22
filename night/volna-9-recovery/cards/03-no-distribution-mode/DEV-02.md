# DEV · 03-no-distribution-mode

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_packing_box_service.py` — назначение заказа теперь учитывает legacy-признак `no-distribution:` так же, как сохранённый признак поставки; старые поставки не обходят запрет.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py` — добавлен регрессионный тест старой поставки с legacy-префиксом.

## Гейты

- `ruff check app/services/fbs_packing_box_service.py tests/test_fbs_packing_box.py` — PASS.
- `mypy .` — FAIL на 17 существующих диагностик в несвязанных файлах; изменённые файлы в выводе отсутствуют.
- `pytest -q tests/test_fbs_packing_box.py` — PASS, 11 passed.
- `pytest` — 816 passed, 5 skipped, 1 unrelated failure: `tests/test_fbs_supply_from_orders.py::test_fbs_cutoff_autoplans_supply_manual_date_and_calendar` получает `deadline_passed` для фиксированной даты 2026-08-15.
- `python3 scripts/ci/back_guard.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/back_guard.py` нет.
- `python3 scripts/ci/check_migrations.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/scripts/ci/check_migrations.py` нет.

## Не реализовано

- Остальные находки ревью относятся к API/OpenAPI, frontend E2E и документации B-09; в этот backend-атом они не входят.

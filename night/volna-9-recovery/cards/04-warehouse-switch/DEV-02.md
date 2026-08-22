# Backend dev · 04-warehouse-switch · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_validator_service.py` — рекомендация склада считает покрытые единицы, а предупреждение возвращает доступное количество на складе-источнике.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_service.py` — выбранный склад участвует в обеих проверках перед созданием; без явного выбора поставка берёт рассчитанный операционный рекомендованный склад, а не legacy-склад заказа.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_stock_availability.py` — регрессия для агрегирования остатков только по операционным складам и точного количества у источника подбора.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — отчёт backend-dev.

## Гейты

- `ruff check` по затронутому backend-набору: пройдено.
- `mypy .`: не пройдено из-за 21 существующей ошибки вне атома; в частности, в неизменённом `fbs_warehouse_binding_service.py` уже есть два нарушения generic-типов.
- `pytest tests/test_fbs_stock_availability.py -q`: пройдено.
- `pytest`: пройдено, 822 теста собраны; процесс завершился с кодом 0.
- `ruff check .`: не пройдено из-за 80 существующих нарушений вне затронутых файлов.
- `back_guard.py`: не запущен — файл `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/back_guard.py` отсутствует в рабочей копии.
- `check_migrations.py`: не запущен по той же причине: файл отсутствует.
- `git diff --check`: пройдено.
- `git commit`: не выполнен — среда запретила создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock` (`Operation not permitted`). Изменения остаются незакоммиченными в этой рабочей копии.

## Не реализовано

- Миграций нет: для атома 2 они не требуются.
- Остальные находки `REVIEW.md` относятся к соседним атомам или frontend-слою и в этом проходе не менялись.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/models/fbs_supply.py` — добавлен стабильный `order_by` для relationship `orders`: `wb_order_id`, затем `order.id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — добавлен интеграционный тест чтения поставки после перемешанной вставки заказов.

## Гейты

- `ruff check .` — не пройден: в исходной backend-базе 82 ранее существовавших нарушения; изменённые файлы отдельно проходят `ruff check`.
- `mypy .` — не пройден: в исходной backend-базе 21 ранее существовавшая ошибка в 6 файлах; новых ошибок в изменённых файлах нет.
- `pytest -q tests/test_fbs_supply_assembly.py -k stable_order` — пройден, 1 тест.
- `pytest -q` — выполняется/результат будет дополнен после завершения запуска.
- `python3 scripts/ci/back_guard.py` — недоступен: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — недоступен: файл отсутствует в этой рабочей копии.

## Не реализовано

- Миграции не требуются: изменение только порядка загрузки relationship и не меняет схему базы данных.
- Остальные фичи карточки не реализованы согласно границе атомарного backend-куска.
- Commit не создан: Git не разрешил запись `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` из-за ограничений рабочей среды.

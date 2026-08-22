# DEV · 08-storage · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0095_product_dimension_events.py` — цепочка миграций продолжена от обязательной `20260821_0094`; журнал наблюдений и снимок действующего источника остаются добавляющей миграцией.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_wb_import_dimensions.py` — добавлена проверка совместного хранения ручной и WB-версий, единственной активной записи и их аудиторского контекста.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/models/product.py app/models/product_dimension_event.py alembic/versions/20260822_0095_product_dimension_events.py tests/test_wb_import_dimensions.py` — успешно, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/models/product.py app/models/product_dimension_event.py` — успешно, `Success: no issues found in 2 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_wb_import_dimensions.py` — успешно, `5 passed in 3.99s`.
- `back_guard.py` не применим: в атоме нет нового маршрута.
- `check_migrations.py` не применим: атом исправляет существующую миграцию, но не добавляет новую.
- `git commit -m "fix(storage): linearize dimensions migration"` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage` — не выполнен: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`).

## Не реализовано

- Находка ревью №9 о синхронизации `dimensions_updated_at` и `dimensions_updated_by_user_id` при WB-импорте и возврате к WB лежит в сервисах `catalog_service.py` и `wildberries_product_import_service.py`, которые буквально принадлежат следующему атому 3. В рамках атома 2 они не изменялись.
- Находки ревью №1–8 и №11–12 относятся к UI, API, расчётам хранения, биллингу, движению и следующим атомам; этот атом их не затрагивает.
- Изменения реализованы локально, но не сохранены Git-коммитом из-за запрета на создание Git lock-файла.

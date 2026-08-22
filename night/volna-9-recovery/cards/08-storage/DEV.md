# DEV · 08-storage · Атом 1: серверная ручка тарифа хранения

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py` — зарегистрирован `POST /operations/storage/tariffs`; доступ ограничен ролью `fulfillment_admin`, ответ — `201` с созданными версиями тарифа.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py` — `create_storage_tariff()` сохраняет общую ставку склада и необязательное исключение селлера одной транзакцией; при конфликте откатывает обе записи.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_tariff_api.py` — покрыты создание общей ставки, исключение селлера с откатом при конфликте второй вставки и запрет для сотрудника с правом `inventory`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md` — отчёт по атому.

## Гейты

Выполнены точные целевые команды:

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_tariff_api.py
```

Результат: `3 passed in 3.70s`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/api/storage.py app/services/storage_statement_service.py tests/test_storage_tariff_api.py
```

Результат: `All checks passed!`.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/api/storage.py app/services/storage_statement_service.py
```

Результат: не пройден из-за пяти существующих ошибок в трёх несвязанных файлах: `app/services/wildberries_credentials_service.py`, `app/services/fbs_stock_sync_service.py`, `app/services/fbs_warehouse_binding_service.py`. В изменённых файлах этого атома ошибок не выведено.

```text
cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ci/back_guard.py
```

Результат: неприменимый скрипт отсутствует в данной рабочей копии (`scripts/ci/back_guard.py: No such file or directory`). Маршрут покрыт новым целевым API-тестом.

Миграции не добавлялись; `check_migrations.py` для этого атома не применяется.

## Не реализовано

Нет. Реализован ровно первый атом из `FEATURES.md`; следующие frontend-атомы не затрагивались.

# DEV · 08-storage · атом 6

## Что реализовано

- `GET /operations/storage/statements` — возвращает операционные склады и черновики выбранного календарного месяца с селлером, SKU, источником и версией объёма, литро-днями, проблемами и нулевыми документами; будущий месяц отклоняется.
- `POST /operations/storage/measurements/rebuild` — сохранён фоновый запуск безопасного пересчёта; повтор задания заменяет только открытый черновик и не создаёт денежные записи.
- `storage_measurement_service` — текущий месяц обрезается по фактическому московскому времени, расчёт использует замороженные `InventoryMovement.seller_id` и `warehouse_id`, неприменённое WB-наблюдение после ручного обмера не меняет объём, неоперационные склады исключены.
- `storage_measurement_service` — исправлено затенение фильтра `seller_id`, из-за которого нулевые документы могли не создаваться для остальных селлеров.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_measurement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_measurement_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Миграции

Нет. Атом использует добавляющий фундамент 07-A, уже присутствующий в ветке: `20260822_0094_inventory_movement_reporting_dimensions.py` замораживает и восстанавливает `seller_id`/`warehouse_id`, а `20260822_0097_storage_movement_scope.py` исключает legacy-склады `FBS WB *` из операционных.

## Тесты

- Расширен `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_measurement_service.py`.
- Проверены: прошлый месяц по умолчанию, невалидный и будущий месяц, формула с долей суток, граница текущего месяца по текущему времени МСК, отрицательный восстановленный остаток, смена версии габаритов, отсутствие ретроактивного объёма, неприменённое WB-наблюдение после ручного обмера, явный возврат WB, отсутствие габаритов, нулевой месяц, идемпотентный повтор фонового задания, чтение результата API и исключение неоперационного склада.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/services/storage_measurement_service.py app/api/storage.py app/tasks/background_jobs.py tests/test_storage_measurement_service.py` — успешно, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/services/storage_measurement_service.py` — успешно, `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy app/api/storage.py app/tasks/background_jobs.py` — в изменённых модулях новых ошибок нет; команда завершается с пятью ошибками зависимостей вне атома: отсутствует внешний `app.models.billing` из 09-A и остаются четыре ранее существующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_measurement_service.py` — успешно, `11 passed in 1.63s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ci/back_guard.py` — неприменим в этой рабочей копии: прямо предписанный файл `scripts/ci/back_guard.py` отсутствует; наличие теста нового маршрута подтверждено целевым pytest выше.
- `git diff --check` — успешно, замечаний нет.
- `git add backend/app/api/storage.py backend/app/services/storage_measurement_service.py backend/tests/test_storage_measurement_service.py night/volna-9-recovery/cards/08-storage/DEV.md && git commit -m 'night(08-storage): repair atom 6 storage drafts'` — не выполнено: sandbox запрещает создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock` (`Operation not permitted`).

## Не реализовано

- Запрет фиксации текущего месяца не менялся: он относится к атому 7 и `storage_statement_service.py`; в этом атоме устранено начисление будущего времени при построении черновика.
- Тариф и денежные суммы не вычисляются: по границе `ARCH-CROSS.md` это внешний контракт 09-A и следующий атом фиксации. Ответ чтения явно отдаёт `tariff_configured=false`, `rate_snapshot=null`, `amount=null` и не создаёт параллельных финансовых сущностей.
- Polling фоновой задачи во frontend не менялся, поскольку роль и атом ограничены backend. Состояние задания доступно через существующий `GET /operations/background-jobs/{job_id}` и проверено API-тестом.

## Находки

- `scripts/ci/back_guard.py` отсутствует в рабочей копии, поэтому обязательную для нового маршрута команду физически нельзя выполнить здесь.
- Целевой mypy для API затрагивает отсутствующий внешний фундамент 09-A и существующие ошибки соседних сервисов; ошибок, указывающих на изменённые строки атома, после исправления типизации DTO нет.

## Блокеры

- Реализация и целевые проверки завершены локально, но результат не сохранён Git-коммитом из-за read-only доступа к служебному каталогу `.git/worktrees`. Требуется выполнить перечисленные `git add` и `git commit` в процессе с правом записи в основной `.git`.

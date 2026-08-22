# Backend dev · 04-warehouse-switch · атом 2 · rework

## Что реализовано

- Эндпоинты: новых эндпоинтов нет; существующий FBS-preflight получает расширенный `stock_preflight.warning_lines[].source_warehouses`.
- Сервис `fbs_supply_validator_service._stock_preflight`: распределяет локальный дефицит товара по нескольким операционным складам в порядке доступного покрытия и возвращает точное количество к подбору с каждого склада.
- Сервис `fbs_supply_validator_service.preflight_to_dict`: сериализует агрегированную разбивку источников; legacy-поле `source_warehouse` заполняется только тогда, когда один склад целиком покрывает локальный дефицит.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_supply_validator_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_stock_availability.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Миграции

Нет: атом не меняет схему данных.

## Тесты

- Усилен `test_preflight_aggregates_operational_stock_and_exposes_source_capacity`: потребность 10 единиц при остатках «Юг» 6 и «Север» 4 даёт одну товарную warning-строку и точную разбивку 6+4.
- Тот же тест подтверждает, что 100 единиц служебного склада не входят в общий остаток, рекомендацию или источники подбора.
- Добавлена проверка сериализованного preflight-ответа: при нескольких источниках ложное одиночное указание отсутствует, а `source_warehouses` содержит оба операционных склада и количества.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && ruff check app/services/fbs_supply_validator_service.py tests/test_fbs_stock_availability.py` — пройдено, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && mypy --follow-imports=skip app/services/fbs_supply_validator_service.py` — пройдено, `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && pytest -q tests/test_fbs_stock_availability.py` — пройдено, `9 passed in 36.32s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git diff --check` — пройдено.
- `back_guard.py` не запускался: новый роут не добавлялся.
- `check_migrations.py` не запускался: миграция не добавлялась.

## Не реализовано

- Frontend-потребление нового списка `source_warehouses` не менялось: роль `backend-dev` запрещает правки UI. Backend больше не возвращает ложный одиночный склад при распределённом покрытии; отображение полной разбивки должен выполнить frontend-атом.
- Остальные находки `REVIEW.md` относятся к frontend, сканеру, отчётности и соседним атомам; этот backend-атом их не затрагивает.

## Блокеры

- Код и отчёт локально реализованы, но отдельный Git-коммит создать невозможно из-за прав среды: `git add -- backend/app/services/fbs_supply_validator_service.py backend/tests/test_fbs_stock_availability.py night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` завершился ошибкой `Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock': Operation not permitted`. Изменения остаются в рабочей копии и пока не имеют восстанавливаемого commit SHA.

## Находки

Нет.

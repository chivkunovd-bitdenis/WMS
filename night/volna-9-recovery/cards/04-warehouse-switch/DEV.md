# Backend dev · 04-warehouse-switch · атом 2 · rework

## Что реализовано

- Эндпоинты: новых эндпоинтов нет; существующий FBS-preflight уже возвращает агрегированные `warning_lines`/`blocking_lines` и точную разбивку `source_warehouses[]` только по операционным складам tenant.
- Сервис `fbs_warehouse_binding_service`: сохранён запрет активной WB→WMS-привязки к служебному складу; устранены ошибки строгой типизации исключения, legacy-проверки служебного склада и ответа сводки пула без изменения поведения.
- Сервисы `fbs_stock_availability_service` и `fbs_supply_validator_service`: проверены без дополнительных изменений — служебный остаток исключён, рекомендация выбирает максимальное покрытие и при равенстве оставляет текущий склад, локальная нехватка предупреждает, а общая нехватка блокирует.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_warehouse_binding_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_stock_availability.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Миграции

Нет: атом не меняет схему данных.

## Тесты

- Усилен `test_preflight_aggregates_operational_stock_and_exposes_source_capacity`: потребность 10 единиц при остатках «Юг» 6 и «Север» 4 даёт одну агрегированную предупреждающую строку, не блокирует создание и сериализует точную разбивку 6+4.
- В том же сценарии 100 единиц служебного склада не входят в общий остаток, рекомендацию или источники подбора.
- Добавлена вторая фаза сценария: при потребности 20 и общем операционном остатке 16 preflight блокирует создание с дефицитом 4; при равном покрытии 6 единиц на текущем складе и «Юге» рекомендацией остаётся текущий склад.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && ruff check app/services/fbs_warehouse_binding_service.py app/services/fbs_stock_availability_service.py app/services/fbs_supply_validator_service.py tests/test_fbs_stock_availability.py` — пройдено, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && mypy --follow-imports=skip app/services/fbs_warehouse_binding_service.py app/services/fbs_stock_availability_service.py app/services/fbs_supply_validator_service.py` — пройдено, `Success: no issues found in 3 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && pytest -q tests/test_fbs_stock_availability.py` — пройдено, `9 passed in 7.56s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git diff --check -- backend/app/services/fbs_warehouse_binding_service.py backend/tests/test_fbs_stock_availability.py` — пройдено без замечаний.
- `back_guard.py` не запускался: новый роут не добавлялся.
- `check_migrations.py` не запускался: миграция не добавлялась.

## Не реализовано

- Находка ревью №1 требует научить frontend читать уже возвращаемый backend-массив `source_warehouses[]`. Файлы `frontend/src/screens/v2/fbsApi.ts` и `frontend/src/screens/v2/FbsSupplyCreateDialog.tsx` не изменялись: роль `backend-dev` запрещает UI-правки. Backend не подменён ложным одиночным `source_warehouse`, потому что при покрытии 6+4 один склад физически не закрывает дефицит.
- Находки ревью №2–6 относятся к другим frontend/backend-атомам и к файлам вне назначенного слоя атома 2; они не затрагивались.
- В `CONTRACT.md` нет отдельного раздела `API и данные`; точный backend-контракт взят из прямо назначенного пользователем атома 2 в `FEATURES.md` и уже принятых решений `RESHENIYA.md`/`ARCH-CROSS.md`. Поведение сверх него не добавлялось.

## Блокеры

- Код и отчёт локально реализованы, но отдельный Git-коммит создать невозможно из-за прав среды: команда `git add -- backend/app/services/fbs_warehouse_binding_service.py backend/tests/test_fbs_stock_availability.py night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` завершилась ошибкой `Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock': Operation not permitted`. Изменения находятся в постоянной рабочей копии, но не имеют нового восстанавливаемого commit SHA.

## Находки

Нет находок по данным, утечкам, секретам или персональным данным; такие источники не открывались.

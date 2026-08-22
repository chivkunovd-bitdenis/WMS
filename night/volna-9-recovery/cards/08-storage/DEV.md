# DEV · 08-storage · атом 5 · переделка по REVIEW

## Что реализовано

- Эндпоинты: нет; атом не добавляет и не меняет HTTP-маршруты.
- Сервис `record_movement_and_adjust_balance`: каждое новое движение фиксирует `seller_id` товара и фактический `warehouse_id` ячейки в момент записи, поэтому дальнейшее изменение товара или ячейки не меняет исторический склад измерения.
- Модель `InventoryMovement`: добавлены замороженный селлер, обязательный склад и признак неполной legacy-разметки; `StorageMeasurement` продолжает ссылаться на границы этих зафиксированных движений.
- Служебные legacy-склады `FBS WB`, `FBS WB *` и склады с кодом `fbs-wb-*` помечаются `is_operational=false` и не входят в обычный состав документов хранения.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/models/inventory_movement.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/inventory_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0095_product_dimension_events.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/alembic/versions/20260822_0097_storage_movement_scope.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_storage_movement_scope.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/tests/test_inventory_movements_report.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md`

## Миграции

- `20260822_0094_inventory_movement_reporting_dimensions` — после внешней ревизии карточки 03 добавляет `seller_id`, обязательный `warehouse_id` и `reporting_dimensions_legacy` в `inventory_movements`, детерминированно заполняет их через товар и ячейку и создаёт индексы отчётных срезов.
- `20260822_0095_product_dimension_events` — изменена только ссылка `down_revision`, чтобы цепочка шла после фундамента 07-A.
- `20260822_0096_storage_measurements_and_statements` — без изменений в переделке; по-прежнему добавляет только неизменяемые измерения и месячные документы без денежных таблиц.
- `20260822_0097_storage_movement_scope` — больше не дублирует `warehouse_id`; добавляет `warehouses.is_operational` и исключает legacy-склады `FBS WB` из операционного контура.

## Тесты

- `test_inventory_movement_has_frozen_storage_dimensions` — обязательность зафиксированного склада и наличие селлера/legacy-признака.
- `test_migrations_backfill_movements_and_exclude_technical_warehouses` — backfill селлера и склада, запрет неразрешённого склада и исключение служебных складов.
- `test_movement_freezes_seller_and_warehouse_at_write_time` — смена селлера товара и склада ячейки после движения не переписывает сохранённые измерения движения.
- `test_inventory_movements_report.py` адаптирован к обязательному `warehouse_id` при прямом создании тестовых движений.
- Повторно проверены пять модельных сценариев уникальности, неизменяемых ссылок и отсутствия денежных колонок из `test_storage_models.py`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && ruff check app/models/inventory_movement.py app/models/storage_measurement.py app/models/storage_statement.py app/services/inventory_service.py tests/test_storage_models.py tests/test_storage_movement_scope.py tests/test_inventory_movements_report.py alembic/versions/20260822_0094_inventory_movement_reporting_dimensions.py alembic/versions/20260822_0095_product_dimension_events.py alembic/versions/20260822_0096_storage_measurements_and_statements.py alembic/versions/20260822_0097_storage_movement_scope.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && mypy --follow-imports=silent app/models/inventory_movement.py app/models/storage_measurement.py app/models/storage_statement.py app/services/inventory_service.py tests/test_storage_movement_scope.py` — `Success: no issues found in 5 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && pytest -q tests/test_storage_models.py tests/test_storage_movement_scope.py tests/test_inventory_movements_report.py` — `10 passed in 3.16s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage && python3 scripts/ci/check_migrations.py` — не выполнен: скрипт отсутствует в этой рабочей копии (`Errno 2`).
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend && alembic heads` — интеграционная проверка остановилась на отсутствующей внешней ревизии `20260821_0094` карточки 03. Ревизия 07-A намеренно сохраняет обязательный порядок `03 -> 07-A -> 08` из `ARCH-CROSS.md` и не подменяет соседнюю миграцию.
- `python3 scripts/ci/back_guard.py` — неприменим: новых роутов нет.
- `git add -- <файлы атома> && git commit -m 'fix(storage): freeze movement warehouse scope'` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-08-storage1/index.lock`: `Operation not permitted`. Изменения локально реализованы, но из-за ограничения sandbox не сохранены в коммите.

## Не реализовано

- Миграция `20260821_0094_fbs_supplies_boxes_without_distribution.py` карточки 03 не копировалась в этот атом: это соседняя продуктовая задача, которая должна быть влита раньше по обязательному порядку волны. До интеграции этой зависимости `alembic heads` в изолированной ветке не проходит.
- Находки REVIEW №1–2 и №4–10 относятся к API, тарифам, расчёту, истории габаритов и frontend, а не к моделям и миграциям атома 5; здесь они не менялись.
- Денежные таблицы, локальные тарифы и отдельный storage-счёт не создавались по прямой границе атома.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой production не читались и не изменялись.

## Находки

- Данных, утечек, секретов или персональных данных в пределах просмотренных файлов не обнаружено.

## Блокеры

- Для кода атома нет. Для общей Alembic-цепочки нужна предусмотренная `ARCH-CROSS.md` предыдущая миграция карточки 03; факт отражён в гейтах и не скрыт под ложным успешным статусом.
- Сохранение результата в Git заблокировано запретом записи в Git metadata основного checkout; восстановимого commit SHA нет.

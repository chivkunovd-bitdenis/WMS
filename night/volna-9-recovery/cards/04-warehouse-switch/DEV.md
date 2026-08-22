# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_picking_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/fbs_packaging_integration_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md

Изменений в `inventory_service.py` и тестах нет: существующий transfer writer уже создаёт обе стороны пары в одной транзакции и заполняет `seller_id`/`warehouse_id` из товара и ячеек.

## Что реализовано

- Подбор из собственной сортировочной ячейки больше не блокируется ложной ошибкой остатка; для межскладской ячейки сохраняется атомарная пара `stock_transfer_out`/`stock_transfer_in` с общим `transfer_group_id`.
- Первый скан блокирует строку поставки `FOR UPDATE`, предотвращая гонку смены склада и подбора.
- Повтор ключа скана проверяет ячейку, товар, заказ и штрихкод; несовпадающий повтор получает `idempotency_key_reused`.
- Упаковка отклоняет строку, чья ячейка сортировки принадлежит другому складу поставки.

## Миграции

Нет.

## Гейты

- ruff: целевые файлы — `All checks passed`; полный `ruff check .` — не пройден из-за 80 уже существующих ошибок в несвязанных файлах.
- mypy: не пройден, 21 существующая ошибка в 6 несвязанных файлах; изменённые сервисы в списке ошибок отсутствуют.
- pytest: целевые `tests/test_fbs_picking.py tests/test_fbs_packaging_integration.py` — `23 passed`; полный прогон остановлен после обнаружения несвязанных падений.
- back_guard.py: не запущен после остановки полного прогона.
- check_migrations.py: не запущен после остановки полного прогона.
- diff --check: пройден.

## Не реализовано

- Добавление новых тестов не потребовалось: существующий backend-набор уже покрывает идемпотентность, undo, сортировочный остаток и запрет списания из чужой сортировки; целевой набор прошёл.
- API preflight, frontend-контекст и UI-блокировки не входят в этот атом backend-dev и не изменялись.

## Блокеры

Нет блокеров по реализации атома. Полные quality-гейты ограничены ранее существовавшими ошибками вне изменённых файлов; секреты, токены и `.env` не читались.

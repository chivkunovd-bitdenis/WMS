# Backend Dev · 06-picking-list-order · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — расширена интеграционная проверка загрузки поставки: заказы с одинаковым `wb_order_id`, вставленные в обратном порядке, возвращаются по `order.id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/models/fbs_supply.py` — без изменений в этом проходе: relationship уже задан как `order_by="(FbsOrder.wb_order_id, FbsOrder.id)"`.

## Гейты

- `ruff check .` (из `backend/`) — не пройден: 82 существующие ошибки вне изменённого атома; `ruff check tests/test_fbs_supply_assembly.py` — пройден.
- `mypy .` (из `backend/`) — не пройден: 21 существующая ошибка в 6 посторонних файлах.
- `pytest` (из `backend/`) — начат, собрано 821 тестов; среда вернула поток без финального итога. Целевой прогон `pytest tests/test_fbs_supply_assembly.py -k 'orders_are_returned_in_stable_order or relationship_orders_by_wb_id_then_internal_id'` — пройден, 2 passed.
- `python3 scripts/ci/back_guard.py` — не запущен: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — не запущен: файл отсутствует в этой рабочей копии.
- `git diff --check` — пройден.

## Не реализовано

- Нет. Находки `REVIEW.md` относятся к печати, API-валидации и фронтенду следующих атомов; этот атом покрывает только стабильный порядок relationship поставки.

## Находки

- Для одного селлера одинаковый `wb_order_id` защищён производственным уникальным ограничением. Тест развязки использует двух селлеров одной организации, не отключая ограничение, и проверяет фактическую загрузку relationship через endpoint поставки.

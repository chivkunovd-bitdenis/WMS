# DEV · 06-picking-list-order · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/models/fbs_supply.py` — relationship `orders` упорядочивает заказы по `wb_order_id`, затем по внутреннему `order.id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — интеграционная проверка стабильного порядка и проверка обоих ключей relationship.

## Гейты

- `ruff check .` — FAIL: 82 уже существующие ошибки в backend, в изменённых файлах ошибок не выявлено.
- `mypy .` — FAIL: 21 уже существующая ошибка в 6 других файлах, изменённые файлы в выводе отсутствуют.
- `pytest -q tests/test_fbs_supply_assembly.py` — PASS: 14 passed, 1 skipped.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в этой рабочей копии.

## Не реализовано

- Других пунктов контракта не реализовывалось: выполнен только атомарный backend-кусок стабильного порядка relationship поставки.
- Миграции не нужны.
- Коллизия `wb_order_id` не может быть создана через текущую БД-тестовую схему из-за уникального ограничения `(seller_id, wb_order_id)`; tie-breaker зафиксирован проверкой конфигурации relationship, а реальная выдача проверена интеграционным тестом.

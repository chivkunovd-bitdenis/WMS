# Backend DEV · 02-verdikt-screen · feature 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/api/fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`

В `GET /operations/fbs-orders/{order_id}/metadata` используется единый серверный
вердикт WB: фиксированная подпись, тон, причина и `delivery_allowed`. Причина
имеет высший приоритет; `pending`, `required`, отсутствие и неизвестное решение
блокируют передачу; `filled`, `optional` и `notRequired` без причины разрешают её.
Агрегация нескольких требований выбирает блокирующее состояние вместо
положительного.

## Миграции

Нет.

## Гейты

- `ruff check app/services/fbs_marking_service.py app/api/fbs_marking.py tests/test_fbs_marking.py` — FAIL: старая неиспользуемая директива `RUF003` в `fbs_marking_service.py`.
- `mypy app/services/fbs_marking_service.py app/api/fbs_marking.py` — FAIL: 4 ранее существующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`.
- `pytest -q tests/test_fbs_marking.py` — PASS: 13 passed.
- `python3 scripts/ci/back_guard.py` — не запущен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/back_guard.py` отсутствует.
- `python3 scripts/ci/check_migrations.py` — не запущен: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/scripts/ci/check_migrations.py` отсутствует.

## Не реализовано

- Серверная защита действия передачи и UI относятся к следующим атомарным
  фичам контракта и не изменялись.

## Блокеры

Нет блокеров реализации; ограничения проверок перечислены в разделе «Гейты».

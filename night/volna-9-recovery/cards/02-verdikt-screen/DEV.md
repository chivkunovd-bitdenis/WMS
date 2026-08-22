# Backend DEV · 02-verdikt-screen · feature 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_shipment_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_shipment_deliver_gate_unit.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

Серверная проверка передачи поставки использует `_wb_order_verdict`, поэтому
одного `check_status`, `assigned`, `pending` или устаревшего флага недостаточно.
Разрешены только `filled`, `optional` и `notRequired` без причины. Причина,
`pending`, `required`, неизвестное и отсутствующее решение блокируют передачу.
Блокирующая проверка содержит UUID конкретного заказа и серверное сообщение с
причиной, если она пришла от WB.

## Миграции

Нет.

## Гейты

- `ruff check .`: FAIL — 82 ошибки в ранее существующих несвязанных файлах; целевые файлы ошибок не добавили.
- `mypy .`: FAIL — 21 ошибка в 6 ранее существующих несвязанных файлах; целевые файлы ошибок не добавили.
- `pytest -q tests/test_fbs_shipment_deliver_gate_unit.py`: PASS — 16 passed.
- `python3 scripts/ci/back_guard.py`: НЕ ЗАПУЩЕН — файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py`: НЕ ЗАПУЩЕН — файл отсутствует в рабочей копии.

## Не реализовано

- UI и API-контракт не изменялись: они относятся к следующим атомарным кускам.
- Полные ruff/mypy не доведены до зелёного состояния из-за несвязанных ошибок репозитория.

## Блокеры

Нет блокеров по реализации. В репозитории отсутствуют два CI-скрипта, а полные
ruff/mypy содержат несвязанные ошибки; целевой тест передачи поставки проходит.

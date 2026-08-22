## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py — единый WB-вердикт и единый признак `delivery_allowed` в metadata API.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py — проверки S-03-TC-001…007 и приоритета блокирующего требования.

API-роуты и модели не менялись: существующий `GET /operations/fbs-orders/{order_id}/metadata` уже возвращает `verdict`.

## Миграции

Нет.

## Гейты

- ruff: `ruff check app/services/fbs_marking_service.py tests/test_fbs_marking.py` — passed.
- mypy: targeted check выявил 4 ранее существующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; в изменённых файлах ошибок не выявлено.
- pytest: `pytest -q tests/test_fbs_marking.py` — 21 passed.
- back_guard.py: не запущен — файл `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- check_migrations.py: не запущен — файл `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии.

## Не реализовано

- UI-части фичи и серверные изменения других карточек не реализовывались по границе атомарной backend-фичи.
- Полные корневые `ruff`, `mypy` и `pytest` не являются зелёными из-за существующих ошибок/регрессий вне изменённых файлов; исправления чужих файлов не вносились.

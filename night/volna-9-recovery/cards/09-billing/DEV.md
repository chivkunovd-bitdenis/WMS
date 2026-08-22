# 09-billing — backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_ledger_service.py` — атомарная запись операционного начисления через savepoint и безопасное разрешение гонки по уникальному событию.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_billing_ledger_service.py` — тестовый savepoint-контекст для сценариев начисления.

## Гейты

- `ruff check .` — FAIL: 83 существующие ошибки вне изменённых файлов.
- `mypy .` — FAIL: 21 существующая ошибка в 6 файлах вне изменённых файлов.
- `pytest -q tests/test_billing_ledger_service.py` — PASS: 2 passed.
- `pytest -q` — прерван после длительного прогона без итогового результата; адресный набор зелёный.
- `python3 scripts/ci/back_guard.py` — FAIL/не доступен: файл `scripts/ci/back_guard.py` отсутствует в checkout.
- `python3 scripts/ci/check_migrations.py` — FAIL/не доступен: файл `scripts/ci/check_migrations.py` отсутствует в checkout.

## Не реализовано

- Остальные находки ревьюера относятся к другим атомам (счета, тарифы, UI, автоматический Celery-выпуск, ИНН, storage) и в этот backend-атом не входят.
- Миграций нет.

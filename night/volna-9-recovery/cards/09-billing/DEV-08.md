# 09-billing — backend-dev · атом 8 после ревью

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py` — единый алгоритм закрытого месяца по календарю МСК, блокировка незакрытого хранения, атомарное разрешение гонки, детализация ledger-источниками и идемпотентное сторно.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/tasks/billing_tasks.py` — ежедневный Celery-запуск: перебор tenant/селлеров и формирование предыдущего месяца.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py` — понятный HTTP 400 для незакрытого/некорректного периода.

## Гейты

- `ruff check app/services/billing_invoice_service.py app/tasks/billing_tasks.py app/api/billing.py` — PASS.
- `mypy app/services/billing_invoice_service.py app/tasks/billing_tasks.py app/api/billing.py` — PASS.
- `pytest -q tests/test_billing_invoice_service.py tests/test_billing_ledger_service.py` — PASS, 4 passed.
- `pytest -q` — полный прогон запущен, но итоговый вывод не получен в доступное время; адресные тесты зелёные.
- `ruff check .` — FAIL на 83 существующих ошибках вне изменённых billing-файлов, включая FBS/WB/scripts.
- `mypy .` — FAIL на существующих ошибках в 7 файлах вне изменённого слоя; изменённые файлы проверены отдельно и проходят.
- `python3 scripts/ci/back_guard.py` — НЕ ДОСТУПЕН: файла нет в checkout.
- `python3 scripts/ci/check_migrations.py` — НЕ ДОСТУПЕН: файла нет в checkout.
- `git diff --check` — PASS.

## Миграции

Нет: схема существующих моделей не менялась.

## Не реализовано

- Полный runtime-тест с реальным `StorageStatement` невозможен в этой копии: модель/таблица `StorageStatement` отсутствует. Сервис использует опубликованный межкарточный маркер `storage_statement` или `storage_statement_closed` в общем ledger.
- Полный интеграционный тест двух настоящих параллельных транзакций и Celery-брокера не добавлен; защита реализована на уникальном ограничении и обработке `IntegrityError`.
- GET-реестр счетов и UI-находки ревью не реализованы: они относятся к frontend/другим атомам.

## Находки

- В рабочем дереве уже было несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/JOURNAL.md`; файл не изменялся этим атомом.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/api/billing.py — добавлены реальные GET-ручки начислений, списка счетов и детализации счета с tenant/admin изоляцией.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_invoice_service.py — пустой месяц и незакрытое хранение блокируют выпуск, строки счета получают стабильный `id`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/tasks/billing_tasks.py — ежедневный запуск догоняет все закрытые месяцы, для которых есть ledger-факты.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/celery_app.py — расписание Celery закреплено за Europe/Moscow.

## Гейты

- ruff — зелёный для изменённых backend-файлов.
- mypy — зелёный для изменённых backend-файлов.
- pytest — адресные billing-тесты: 7 passed; полный запуск начат, в этой сессии остановился на длительном прогоне после 16% без финального результата.
- back_guard.py — не выполнен: файл отсутствует в этой рабочей копии.
- check_migrations.py — не выполнен: файл отсутствует в этой рабочей копии.

## Не реализовано

- Полная переоценка ранее `unpriced` ledger-строк после добавления тарифа не внесена: immutable ledger не должен переписывать исторический факт; повторный выпуск остаётся заблокированным до отдельного решения алгоритма ретарификации.
- Подключение `record_reversal` к конкретному бизнес-событию отмены не менялось: в разрешённом атоме нет названного backend-пути отмены складской операции.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

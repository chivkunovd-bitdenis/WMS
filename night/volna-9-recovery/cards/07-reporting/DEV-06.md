# Backend Dev · 07-reporting · защищённая сводка

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/services/reporting_service.py` — агрегация сводки, полуоткрытый период, сравнение с предыдущим интервалом и дневные серии.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/api/reports.py` — read-only `GET /reports/overview` с tenant/seller scope и проверкой прав.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/app/main.py` — регистрация роутера отчётов.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/backend/tests/test_reports_overview.py` — проверки авторизации и отказа при периоде длиннее 366 дней.

## Реализовано

- `GET /reports/overview` возвращает текущий остаток, внешний приход/расход, сравнение с предыдущим равным интервалом, дневные серии, `generated_at`, свежесть источника и предупреждения.
- Даты обрабатываются как полуоткрытый интервал `[date_from, date_to)`; интервал длиннее 366 дней отклоняется.
- Внутренние движения исключаются из потоковых итогов по `transfer_group_id`; seller-пользователь ограничивается своим seller scope, а доступ проверяется через существующий `inventory`/`can_products` guard.

## Гейты

- `ruff check app/services/reporting_service.py app/api/reports.py tests/test_reports_overview.py app/main.py` — GREEN.
- `mypy app/services/reporting_service.py app/api/reports.py` — GREEN.
- `pytest -q tests/test_reports_overview.py` — GREEN, 2 passed.
- `ruff check .` — RED на 87 существующих нарушениях в несвязанных файлах; собственные файлы проходят.
- `mypy .` — не выполнен после полного ruff, целевой mypy для изменённых модулей GREEN.
- `pytest` — полный набор не выполнен; целевые тесты GREEN.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии.

## Не реализовано

- Поле `Warehouse.is_operational` отсутствует в текущей схеме и не входит в разрешённые файлы этого атома; текущий расчёт остатка использует строки `InventoryBalance` через существующие склады. Добавление поля/миграции оставлено следующей зависимой фиче.
- Свежесть внешнего Wildberries-источника не подключалась: в ответе возвращается `null`, предупреждения пусты, так как контракт не указал существующий источник этой метрики.
- Полный tenant/seller сценарий с transfer-парами не добавлялся в тесты этого атома; фильтрация `transfer_group_id` реализована в сервисе.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.
- Несвязанные изменения в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-07-reporting/night/volna-9-recovery/JOURNAL.md` не затрагивались.

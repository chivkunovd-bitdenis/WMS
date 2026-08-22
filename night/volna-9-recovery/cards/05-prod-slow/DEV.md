## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_autopoll_service.py — single-flight теперь использует отдельный PostgreSQL advisory lock для пары `(seller_id, sync_kind)`; `new` и `reconcile` не блокируют друг друга.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/celery_app.py — удалено старое дублирующее расписание `fbs-orders-autopoll`; оставлены независимые интервалы 180 секунд и 3600 секунд.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py — добавлены проверки отсутствия старого beat-контурa и различия межпроцессных lock-ключей для двух видов синхронизации.

## Гейты

- `ruff check .` — FAIL на существующих нарушениях в несвязанных файлах; изменённый тест после исправления `SIM117` не добавляет замечаний.
- `mypy .` — FAIL на существующих ошибках в `inventory_movement_report_service.py`, `wildberries_credentials_service.py`, cleanup-скриптах и `fbs_stock_sync_service.py`; изменённые файлы в выводе отсутствуют.
- `pytest -q` — выполняется/результат будет дополнен после завершения полного прогона; целевые `tests/test_wb_marketplace_orders_service.py tests/test_fbs_autopoll.py` проходят.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии (`file not found`).
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии (`file not found`); миграций в атоме нет.
- Commit — BLOCKED: Git не разрешил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` (`Operation not permitted`); изменения сохранены в рабочем дереве и перечислены ниже.

## Не реализовано

- Пункты ревью 1–2 и 7–15 относятся к печатной фоновой ленте или frontend-экранам и не входят в этот backend-атом.
- Миграции — нет.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

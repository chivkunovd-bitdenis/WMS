# Backend dev · 05-prod-slow · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wb_marketplace_orders_service.py` — часовая сверка WB прекращает обход с retryable-ошибкой `cursor_cycle`, если WB повторяет ранее выданный `next_token`; дублирующая страница не записывается и привязка поставок не выполняется.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py` — проверки раздельного запуска Celery-задач `new`/`reconcile`, single-flight по `(seller_id, sync_kind)`, отсутствия seller-wide lock в job-пути и повторного курсора.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — этот отчёт.

## Гейты

- ruff: адресно PASS (`ruff check app/services/wb_marketplace_orders_service.py tests/test_wb_marketplace_orders_service.py`); полный `ruff check .` FAIL — 79 существующих нарушений вне атома.
- mypy: полный `mypy .` FAIL — 21 существующая ошибка в 6 несвязанных файлах; адресный запуск также получает 4 ошибки из импортируемых несвязанных сервисов, изменённые файлы ошибок не добавили.
- pytest: адресно PASS — `tests/test_wb_marketplace_orders_service.py`, 15 passed. Полный `pytest -q` дважды прервался средой после 5–6 тестов без итогового статуса; лог `/private/tmp/volna-9-05-prod-slow-pytest.log` содержит только точки, поэтому полный результат не заявляется.
- back_guard.py: не запущен — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/scripts/ci/back_guard.py` отсутствует в рабочей копии.
- check_migrations.py: не запущен — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/scripts/ci/check_migrations.py` отсутствует в рабочей копии.
- Миграции: нет.

## Не реализовано

- Backend-находки ревью №3 и все проверки атома 2 устранены. Фронтенд-находки №1, №4–10 относятся к другим разрешённым файлам и не менялись в роли backend-dev.
- Git-коммит не создан: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` (`Operation not permitted`), поэтому изменения сохранены только в рабочем дереве.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

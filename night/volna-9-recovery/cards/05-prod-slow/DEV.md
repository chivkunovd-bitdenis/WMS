# Backend dev · 05-prod-slow · атом 1

## Изменённые файлы

- Нет: продуктовый backend-код и тесты не изменялись.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — этот отчёт.

## Гейты

- ruff: FAIL, 79 существующих нарушений вне атома; файлы атома не менялись.
- mypy: FAIL, 21 существующая ошибка в 6 несвязанных файлах; файлы атома не менялись.
- pytest: целевой `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py` — PASS, 12 passed. Полный запуск собрал 830 тестов, но его итог в доступном выводе не был получен; поэтому полный gate не подтверждён.
- back_guard.py: не запускался — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/scripts/ci/back_guard.py` отсутствует в рабочей копии.
- check_migrations.py: не запускался — `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/scripts/ci/check_migrations.py` отсутствует в рабочей копии.

## Не реализовано

- Атом 1 не реализован. В обязательном входном файле `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/CONTRACT.md` отсутствует раздел «API и данные», поэтому backend-dev не может менять поведение `new`/`reconcile` или трактовать ошибку повторного `next_token` из ревью как утверждённый API-контракт.
- Релевантная находка ревью №3 зафиксирована: полная сверка не защищена от повторяющегося `next_token`; её исправление требует явного серверного контракта для результата и ошибки обхода.
- Отдельный Git-коммит не создан: Git отказал в создании `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` с `Operation not permitted`. Артефакт остаётся незакоммиченным в рабочей копии.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

# DEV · 01-wb-marking · backend-dev · feature 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py` — фоновая сверка собирает уникальные `wb_order_id`, последовательно режет их на пачки максимум по 100, после ошибки продолжает следующую пачку и сопоставляет строки ответа с заказом по `order_id`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — применение принимает уже загруженный batch-ответ; ручной путь сохраняет запрос пачкой из одного ID.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт backend-dev.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_autopoll.py` — целевые тесты прошли: 20 passed; проверены batch-вызовы, ограничение 100, дедупликация, продолжение после ошибки и применение ответа по `order_id`.

## Гейты

- `ruff check .` — FAIL: 80 существующих ошибок в backend, вне изменённых файлов атома.
- `mypy .` — FAIL: 21 существующая ошибка в 6 файлах, вне изменённых файлов атома.
- `pytest -q tests/test_fbs_marking.py tests/test_fbs_autopoll.py` — PASS: 20 passed.
- `pytest -q` — выполнялся; полный итог не получен в доступном окне выполнения, поэтому не засчитываю как PASS.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии; миграций нет.

## Не реализовано

- Новых API-эндпоинтов, миграций и изменений расписания нет — они не требуются атомом 4.
- Кодовый diff по сервисам не создавался в этом проходе: требуемая реализация уже находилась в рабочей копии до запуска backend-dev и подтверждена целевыми тестами.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

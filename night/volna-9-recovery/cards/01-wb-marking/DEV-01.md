# DEV · 01-wb-marking · backend-dev · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py` — batch DTO сохраняет `decision`, `value` и `reason`; первый ответ `429` ожидает числовой `Retry-After` и повторяет ту же пачку ровно один раз. Реализация уже находилась в текущем `HEAD`, дополнительный backend-дифф не потребовался.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py` — тесты полного `metaDetails`, единственного повтора `429`, ошибок `4xx/5xx` и неразбираемого ответа уже находились в текущем `HEAD`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт этого запуска.

## Миграции

Нет.

## Тесты

- `tests/test_wildberries_marketplace_fbs_client.py`: 17 тестов — сохранение `decision/value/reason`, повтор batch-запроса ровно один раз после `429`, отсутствие повторов для `4xx/5xx`, отказ на неразбираемом теле и ограничение пачки 100.

## Гейты

- `ruff check app/services/wildberries_fbs_client.py tests/test_wildberries_marketplace_fbs_client.py` — PASS.
- `mypy app/services/wildberries_fbs_client.py` — PASS.
- `pytest -q tests/test_wildberries_marketplace_fbs_client.py` — PASS: 17 passed.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии, код завершения 2.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии, код завершения 2; миграций нет.

## Не реализовано

- Ничего из атома 1: требуемое поведение уже присутствует в `HEAD`; остальные атомы карточки не затрагивались.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не изменялись.

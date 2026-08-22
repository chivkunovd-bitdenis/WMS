# DEV · 01-wb-marking · атом 1 · rework

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: batch-чтение `metaDetails` сохраняет `key`, `value`, `decision` и `reason`; при `429` один раз ожидает `Retry-After` (число или HTTP-дата) и повторяет ту же пачку не более 100 заказов.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: ответы 4xx/5xx и неразбираемое тело возвращают ошибку без частичного успешного результата.

## Миграции

- Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py`: полный DTO `decision`/`value`/`reason`, один повтор после `429`, числовой и HTTP-date `Retry-After`, ошибки 400/500 и неразбираемый успешный ответ.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status`: адресная регрессия вызывающего контура.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

Backend-код атома уже сохранён в истории текущей ветки коммитом `8e8f2a3e9908956550eb8cb3278ec137d404f8ba`; повторная проверка `JUDGE.md` не выявила замечаний в файлах и backend-слое этого атома, поэтому необоснованный кодовый diff не создавался.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/wildberries_fbs_client.py tests/test_wildberries_marketplace_fbs_client.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/wildberries_fbs_client.py` — PASS: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_wildberries_marketplace_fbs_client.py` — PASS: `19 passed in 0.07s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status` — PASS: `1 passed in 1.10s`.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не запускался: атом не добавляет и не меняет маршруты.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграции.

## Не реализовано

- Единственная находка `JUDGE.md` — неподнятый живой UI-стенд и отсутствие browser evidence для зон `S-03`, `S-14`, `S-15` — не относится к разрешённым backend-файлам и слою атома 1; backend-изменений для неё нет.
- Новые маршруты, миграции, изменение расписания, UI и обращения к живому кабинету Wildberries не добавлялись.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Backend-блокеров атома нет. Общий карточный статус остаётся `SCREEN_VERDICT: BLOCKED` из-за отсутствующего живого browser review, что находится вне роли `backend-dev`.

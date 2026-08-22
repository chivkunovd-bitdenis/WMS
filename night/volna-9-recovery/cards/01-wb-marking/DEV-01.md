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

Backend-код атома уже сохранён в текущей ветке коммитом `8e8f2a3e9908956550eb8cb3278ec137d404f8ba`; повторная проверка `JUDGE.md` не выявила замечаний в файлах и слое этого атома.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/wildberries_fbs_client.py tests/test_wildberries_marketplace_fbs_client.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/wildberries_fbs_client.py` — PASS: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_wildberries_marketplace_fbs_client.py` — PASS: `19 passed in 0.06s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status` — PASS: `1 passed in 0.96s`.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не применим: роуты не добавлялись и не менялись.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не применим: миграции не добавлялись.
- `git add night/volna-9-recovery/cards/01-wb-marking/DEV.md && git commit -m "night(01-wb-marking): verify atom 1 rework" -- night/volna-9-recovery/cards/01-wb-marking/DEV.md` — FAIL до изменения индекса: sandbox запретил создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock` (`Operation not permitted`).

## Не реализовано

- Замечание `JUDGE.md` о недоступном живом UI относится к browser-product-review экранов S-03, S-14 и S-15. Этот backend-атом не меняет UI, поэтому исправлений в его файлах и слое нет.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Backend-код атома сохранён в Git-коммите `8e8f2a3e9908956550eb8cb3278ec137d404f8ba`, но обновлённый `DEV.md` остаётся незакоммиченным из-за read-only доступа sandbox к общему Git metadata. Browser-product-review остаётся отдельной проверкой живого UI.

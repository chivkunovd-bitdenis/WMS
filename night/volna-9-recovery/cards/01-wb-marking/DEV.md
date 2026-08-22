# DEV · 01-wb-marking · backend-dev · атом 2

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py` — проверено: `EVENT_WB_ORPHANED` объявлен и входит в `MARKING_CODE_EVENT_TYPES`; код, статус и пул при записи события не изменяются.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py` — проверено: тест создаёт `wb_orphaned` через существующий журнал и подтверждает сохранность статуса, пула и товарной привязки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт этого запуска.

Реализационный код и тест уже были в текущем `HEAD` (`5ae86fe`); дополнительный diff в backend для этого атома не потребовался.

## Миграции

Нет: используется существующий журнал событий, схема не меняется.

## Тесты

- `backend/tests/test_marking_code_events.py::test_wb_orphaned_event_is_recorded_without_releasing_code` — запись допустимого события и проверка неизменности статуса, `pool_id` и `product_id`.

## Гейты

- `ruff check backend/app/models/marking_code.py backend/tests/test_marking_code_events.py` — PASS.
- `mypy backend/app/models/marking_code.py` — PASS.
- `pytest -q backend/tests/test_marking_code_events.py` — PASS: 3 passed.
- `ruff check .` из `backend/` — FAIL: 80 ранее существующих ошибок в несвязанных файлах.
- `mypy .` из `backend/` — FAIL: 21 ранее существующая ошибка в 6 несвязанных файлах.
- `pytest -q` из `backend/` — запущен; полный прогон длительный, на момент оформления артефакта продолжался, целевой тест зелёный.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии.

## Не реализовано

- Ничего из контракта атома 2: `wb_orphaned` уже поддерживался существующей моделью и тестом; новые таблицы и миграции не нужны.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не изменялись.

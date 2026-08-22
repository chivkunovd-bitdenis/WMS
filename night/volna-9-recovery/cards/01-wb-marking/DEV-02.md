# DEV · 01-wb-marking · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py` — проверено: `EVENT_WB_ORPHANED` уже входит в допустимые типы событий журнала.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py` — проверено: тест создаёт событие через существующий журнал и подтверждает сохранность статуса, пула и привязки к товару.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт backend-dev.

Реализационный код и тест уже были в `HEAD`; дополнительный diff в backend для этой атомарной фичи не требуется.

## Гейты

- `ruff check .` — FAIL: 80 существующих ошибок в несвязанных файлах backend.
- `mypy .` — FAIL: 21 существующая ошибка в 6 несвязанных файлах.
- `pytest` — полный прогон начат, но остановлен после прохождения 6% из-за длительного выполнения; целевой `tests/test_marking_code_events.py` прошёл: 3 теста.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в этой рабочей копии.

## Не реализовано

- Ничего из контракта этой атомарной фичи: `wb_orphaned` и проверка записи в существующий журнал уже присутствуют в исходном `HEAD`; новые таблицы и миграции не нужны.

## Блокеры

- Полный набор гейтов не зелёный из-за ранее существующих ошибок и отсутствующих CI-скриптов; исправления вне атомарной карточки не вносились.

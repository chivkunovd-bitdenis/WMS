# DEV · 01-wb-marking · атом 2/5 (повторная проверка после JUDGE)

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервисы: новых и изменённых сервисов нет; атом расширяет допустимые типы существующего журнала КИЗ.
- Модель `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py`: `EVENT_WB_ORPHANED` включён в `MARKING_CODE_EVENT_TYPES`.
- Журнал КИЗ принимает `wb_orphaned` для исходного `MarkingCode`; добавление записи не освобождает код и не меняет его статус, пул или продуктовую привязку.

## Миграции

Нет: `event_type` уже является строковым полем существующей таблицы `marking_code_events`, поэтому новый допустимый тип не меняет схему.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py`: `test_wb_orphaned_event_is_recorded_without_releasing_code` создаёт событие через существующую модель и проверяет `code_id`, пул, статус и продуктовую привязку КИЗ.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/models/marking_code.py tests/test_marking_code_events.py` — PASS, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/models/marking_code.py` — PASS, `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_marking_code_events.py::test_wb_orphaned_event_is_recorded_without_releasing_code` — PASS, `1 passed in 0.90s`.
- `python3 scripts/ci/back_guard.py` — не применим: атом не добавляет и не меняет роуты.
- `python3 scripts/ci/check_migrations.py` — не применим: атом не добавляет миграцию.

## Не реализовано

- Повторная и конкурентная дедупликация `wb_orphaned` не входит в этот атом: её реализует следующая фича сверки без новой таблицы или миграции.
- Из `JUDGE.md` нет находок в модели, журнале или тесте этого атома. Единственная находка — недоступность живого UI-стенда для browser-проверки — относится к отдельной продуктовой проверке и не требует backend-изменений.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

Нет для backend-атома. Живой browser-review остаётся заблокированным по причине из `JUDGE.md`; это не меняет результат целевых backend-гейтов.

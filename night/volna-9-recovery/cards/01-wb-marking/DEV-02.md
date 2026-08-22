# DEV · 01-wb-marking · атом 2/5 · rework после JUDGE

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервисы: новых и изменённых сервисов нет; атом расширяет допустимые типы существующего журнала КИЗ.
- Модель `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py`: событие `EVENT_WB_ORPHANED = "wb_orphaned"` входит в `MARKING_CODE_EVENT_TYPES`.
- Существующий журнал `MarkingCodeEvent` принимает `wb_orphaned` с сохранением ссылки на исходный КИЗ и пул. Запись события сама по себе не меняет статус, пул или продуктовую привязку кода и не освобождает его.
- Код и тест атома уже сохранены в истории текущей ветки коммитами `5ae86fe8018170fc68064e87b5815f8cb8af0fd3` и `acb19c362589b5544d961eda1b75e896790a3388`.

## Миграции

- Нет. Поле `marking_code_events.event_type` уже хранится как `String(32)`, поэтому новый допустимый тип события не меняет схему данных.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py::test_wb_orphaned_event_is_recorded_without_releasing_code` создаёт `wb_orphaned` через существующую модель журнала и проверяет тип события, ссылку на КИЗ, пул, статус и продуктовую привязку после сохранения.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py` — реализация атома уже находится в истории ветки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py` — целевой тест атома уже находится в истории ветки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — восстановлен обязательный отчёт текущего атома после удаления внешним процессом.

В текущем rework backend-файлы не менялись: `JUDGE.md` не содержит находок в модели, журнале или тесте этого атома, поэтому необоснованный кодовый diff не создавался.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/models/marking_code.py tests/test_marking_code_events.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/models/marking_code.py` — PASS: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_marking_code_events.py::test_wb_orphaned_event_is_recorded_without_releasing_code` — PASS: `1 passed in 1.49s`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не запускался: атом не добавляет и не меняет роуты.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию.

## Не реализовано

- Повторная и конкурентная дедупликация `wb_orphaned` не входит в этот атом: по `FEATURES.md` её покрывает следующая фича сверки без новой таблицы или миграции.
- Единственная находка `JUDGE.md` — недоступность живого UI-стенда и отсутствие браузерных снимков экранов `S-03`, `S-14`, `S-15`. Она не относится к backend-файлам или слою этого атома и не требует изменения модели либо теста.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Нет для backend-атома. Браузерная продуктовая проверка остаётся отдельным этапом согласно `JUDGE.md`.

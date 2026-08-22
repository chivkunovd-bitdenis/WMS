# DEV · 01-wb-marking · атом 2/5

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервис: новых и изменённых сервисов нет; атом расширяет существующий журнал КИЗ на уровне модели.
- Модель `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py`: тип события `wb_orphaned` включён в допустимый набор `MARKING_CODE_EVENT_TYPES`.
- Журнал КИЗ принимает событие `wb_orphaned`, связанное с исходным `MarkingCode`; создание события не меняет жизненный статус кода, его пул и продуктовую привязку.

## Миграции

Нет: `event_type` уже хранится в строковом поле существующей таблицы журнала, поэтому новый допустимый тип не требует изменения схемы базы данных.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py`: `test_wb_orphaned_event_is_recorded_without_releasing_code` создаёт `wb_orphaned` через существующую модель журнала и проверяет тип события, связь `code_id`, прежние статус, пул и продуктовую привязку КИЗ.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/models/marking_code.py tests/test_marking_code_events.py` — PASS, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/models/marking_code.py` — PASS, `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_marking_code_events.py::test_wb_orphaned_event_is_recorded_without_releasing_code` — PASS, `1 passed in 4.95s`.
- `back_guard.py` — не применим: атом не добавляет и не меняет роуты.
- `check_migrations.py` — не применим: атом не добавляет миграцию.

## Не реализовано

- Конкурентная и повторная дедупликация `wb_orphaned` не реализовывалась в этом атоме: `FEATURES.md` прямо относит повторную запись для той же привязки к следующей фиче сверки и запрещает ради неё новую таблицу или миграцию.
- Находки 1–3 из `REVIEW.md` относятся к `/backend/app/services/fbs_marking_service.py` и тестам следующего сервисного атома, а не к модели и журналу атома 2.
- Находка 4 из `REVIEW.md` требует конкурентного сценария сервиса сверки в `/backend/tests/test_fbs_kiz.py`; этот файл и поведение находятся за границей текущего атома 2.

## Находки

- В `CONTRACT.md` нет отдельного заголовка `API и данные`; backend-граница атома буквально задана в `FEATURES.md` и подтверждена `ARCH-CROSS.md`: карточка 01 владеет семантикой `metaDetails` и не освобождает КИЗ автоматически.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Backend-изменения атома сохранены в достижимых коммитах: основная модель и тест — `5ae86fe8018170fc68064e87b5815f8cb8af0fd3`, дополнительные проверки связи события после ревью — `acb19c362589b5544d961eda1b75e896790a3388`.
- Обновлённый обязательный отчёт `DEV.md` создан локально, но сохранить его отдельным коммитом в этой сессии невозможно: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock`, потому что метаданные worktree находятся вне разрешённой для записи области песочницы (`Operation not permitted`).

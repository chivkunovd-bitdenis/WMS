# DEV · 01-wb-marking · backend-dev · атом 2 (rework)

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_marking_code_events.py` — усилена проверка записи `wb_orphaned`: аудит-событие сохраняет допустимый тип и ссылку на исходный КИЗ, не меняя статус, пул или товар КИЗ.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/models/marking_code.py` — в базовом коммите этого атома уже определены `EVENT_WB_ORPHANED` и его допустимость в `MARKING_CODE_EVENT_TYPES`; повторная правка модели не потребовалась.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт rework-прохода.

## Гейты

- `ruff check backend/app/models/marking_code.py backend/tests/test_marking_code_events.py` — PASS.
- `mypy backend/app/models/marking_code.py backend/tests/test_marking_code_events.py` — PASS.
- `pytest -q backend/tests/test_marking_code_events.py` — PASS.
- `ruff check .` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — FAIL: 80 уже существующих ошибок вне изменённых файлов.
- `mypy .` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — FAIL: 21 уже существующая ошибка в шести посторонних файлах.
- `pytest` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — итог не получен: запуск собрал 827 тестов и начал выполнение, но среда прекратила возврат вывода до финального статуса; целевой набор прошёл.
- `python3 scripts/ci/back_guard.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` в рабочей копии нет.
- `python3 scripts/ci/check_migrations.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` в рабочей копии нет; миграции не добавлялись.

## Не реализовано

- Замечание review №7 о проверке вызова `wb_orphaned` из сервисной сверки не менялось: этот вызов и сценарии `missing`/`replacement_required` принадлежат следующему атому 3 в `backend/app/services/fbs_marking_service.py`. В границе атома 2 покрыта допустимость и сохранение самого события в существующем журнале.
- Прочие замечания `REVIEW.md` относятся к атомам 1, 3 и 4; этот проход не затрагивает соседние сервисы.

## Находки

- Секреты, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не изменялись.

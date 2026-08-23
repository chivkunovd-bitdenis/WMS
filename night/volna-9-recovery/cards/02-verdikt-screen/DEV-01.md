# DEV · 02-verdikt-screen · атом 1 · повторное исправление

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет; контракт API не менялся.
- Сервис: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py` сохраняет маркер старта WB-проверки отдельной короткой транзакцией до ожидания WB; ответ раннего запроса больше не может записать операторский вердикт после старта более нового запроса.
- Сервис: блокировка текущего состояния продолжает возвращать уже загруженные связи `order.markings` и `marking_code`, поэтому повторно проверенные сценарии замены ЧЗ не выполняют ленивое async-чтение.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py::test_fbs_marking_sync_does_not_apply_stale_response` проверяет оба порядка завершения запросов A и B. При завершении A первым его устаревший `filled` не открывает сдачу, а итог B сохраняет `uinBadStatus` и `metadata_delivery_allowed = false`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py` проверяет три прямо названные регрессии замены ЧЗ и согласованное ожидание успешного WB-ответа: сохранение предыдущего кода, отсутствие двойного счётчика и выбор активной строки.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m ruff check app/services/fbs_marking_service.py tests/test_fbs_marking.py tests/test_fbs_kiz.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m mypy --follow-imports=silent app/services/fbs_marking_service.py` — `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_does_not_apply_stale_response tests/test_fbs_kiz.py::test_fbs_kiz_commit_success_creates_records_event_and_counter tests/test_fbs_kiz.py::test_fbs_kiz_commit_confirmed_replaces_old_kiz_and_voids_code tests/test_fbs_kiz.py::test_fbs_kiz_pool_to_external_replacement_does_not_double_count_unit tests/test_fbs_kiz.py::test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row` — `6 passed in 10.29s`.
- `back_guard.py` не запускался: атом не добавляет и не меняет роуты.
- `check_migrations.py` не запускался: миграций нет.
- Полный backend-регресс, `ruff check .` и `mypy .` не запускались по правилу атомарного шага.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && git add -- backend/app/services/fbs_marking_service.py backend/tests/test_fbs_marking.py backend/tests/test_fbs_kiz.py night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — не выполнена: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`, `Operation not permitted`.

## Не реализовано

- Находки 4–6 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/REVIEW.md` относятся к frontend-слою и не входят в роль backend-dev или этот атом.
- Новые роуты, модели, колонки и миграции не добавлялись: атом реализует защиту порядка существующих проверок WB без изменения API и схемы данных.

## Находки

Нет новых находок по данным, утечкам, секретам или персональным данным. Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.

## Блокеры

Git-сохранение блокируется правами среды на служебный каталог зарегистрированного worktree: нельзя создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`. Реализация и DEV-артефакт присутствуют локально, но новый восстанавливаемый commit SHA не создан.

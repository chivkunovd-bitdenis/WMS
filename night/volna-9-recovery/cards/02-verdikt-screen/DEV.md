# DEV · 02-verdikt-screen · атом 2 · повторная проверка

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет; API-контракт не менялся.
- Сервис: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py` при блокировке актуального состояния заранее загружает `FbsOrderMarking.marking_code` и восстанавливает `order.markings` из полученного набора без ленивого async-чтения. Подтверждённая замена ЧЗ после ответа WB больше не завершается `MissingGreenlet`.

## Миграции

Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py::test_fbs_kiz_commit_confirmed_replaces_old_kiz_and_voids_code` проверяет штатную замену и погашение прежнего ЧЗ.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py::test_fbs_kiz_pool_to_external_replacement_does_not_double_count_unit` проверяет, что замена пулового ЧЗ внешним сохраняет счётчик в одну единицу.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_kiz.py::test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row` проверяет выбор активной строки при доступных загруженных связях.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py` — реализация атома сохранена в существующем commit `06b62a2dd400962db56b6cfd36605055caaceb04`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — отчёт повторной проверки.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m pytest -q tests/test_fbs_kiz.py::test_fbs_kiz_commit_confirmed_replaces_old_kiz_and_voids_code tests/test_fbs_kiz.py::test_fbs_kiz_pool_to_external_replacement_does_not_double_count_unit tests/test_fbs_kiz.py::test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row` — `3 passed in 2.59s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m ruff check app/services/fbs_marking_service.py tests/test_fbs_kiz.py` — `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m mypy --follow-imports=silent app/services/fbs_marking_service.py` — `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && git diff --check -- backend/app/services/fbs_marking_service.py backend/tests/test_fbs_kiz.py night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — замечаний нет.
- `back_guard.py` не запускался: атом не добавляет и не меняет роуты.
- `check_migrations.py` не запускался: миграций нет.
- Полный backend-регресс, `ruff check .` и `mypy .` не запускались по правилу атомарного шага.

## Не реализовано

- Находка 1 повторного ревью относится к отдельному атомарному пункту 1 и уже сохранена в commit `16bbe667`; в этом атоме не менялась.
- Находка 3 относится к отдельному пункту 3 из `FEATURES.md`; она не входит в текущий атом 2.
- Находки 4–6 относятся к frontend-слою и не входят в роль backend-dev.

## Находки

Нет новых находок по данным, утечкам, секретам или персональным данным. Секреты, ключи, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.

## Блокеры

Повторное сохранение DEV-артефакта отдельным commit недоступно: команда `git add -- night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` не смогла создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock` (`Operation not permitted`). Реализация сервиса уже сохранена в commit `06b62a2dd400962db56b6cfd36605055caaceb04`; текущий DEV-артефакт существует локально в этой рабочей копии.

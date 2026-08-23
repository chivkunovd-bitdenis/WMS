# DEV · 02-verdikt-screen · атом 2

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет; контракт API не менялся.
- Сервис: `_lock_current_marking_state` по-прежнему перечитывает и блокирует актуальные строки заказа и ЧЗ, но теперь восстанавливает `order.markings` из уже загруженного набора без ленивого async-запроса.
- Сервис: связь `FbsOrderMarking.marking_code` загружается вместе с заблокированными строками, поэтому подтверждённая замена после ответа WB штатно погашает прежний код и не получает `MissingGreenlet`.

## Миграции

Нет.

## Тесты

- Новые тесты не добавлялись: находка уже была воспроизведена тремя прямо назначенными регрессиями в `backend/tests/test_fbs_kiz.py`.
- `test_fbs_kiz_commit_confirmed_replaces_old_kiz_and_voids_code` подтверждает успешную замену, статус `void` прежнего кода, событие погашения и один учтённый внешний ЧЗ.
- `test_fbs_kiz_pool_to_external_replacement_does_not_double_count_unit` подтверждает, что при замене пулового ЧЗ внешним суммарный счётчик остаётся равен одной единице.
- `test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row` подтверждает доступность уже загруженной `order.markings` и выбор активной строки вместо более новой отклонённой.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Гейты

- Воспроизведение находки до исправления: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m pytest -q tests/test_fbs_kiz.py::test_fbs_kiz_commit_confirmed_replaces_old_kiz_and_voids_code tests/test_fbs_kiz.py::test_fbs_kiz_pool_to_external_replacement_does_not_double_count_unit tests/test_fbs_kiz.py::test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row` — `3 failed in 3.99s`; все три падения содержали `sqlalchemy.exc.MissingGreenlet`.
- Целевой pytest после исправления: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m pytest -q tests/test_fbs_kiz.py::test_fbs_kiz_commit_confirmed_replaces_old_kiz_and_voids_code tests/test_fbs_kiz.py::test_fbs_kiz_pool_to_external_replacement_does_not_double_count_unit tests/test_fbs_kiz.py::test_fbs_marking_readers_prefer_active_row_over_newer_rejected_row` — `3 passed in 3.27s`.
- Ruff: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m ruff check app/services/fbs_marking_service.py` — `All checks passed!`.
- Mypy: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m mypy --follow-imports=silent app/services/fbs_marking_service.py` — `Success: no issues found in 1 source file`.
- Проверка diff: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && git diff --check -- backend/app/services/fbs_marking_service.py night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — замечаний нет.
- Сохранение в Git: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && git add -- backend/app/services/fbs_marking_service.py night/volna-9-recovery/cards/02-verdikt-screen/DEV.md` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`, `Operation not permitted`.
- `back_guard.py` не запускался: атом не добавляет и не меняет роуты.
- `check_migrations.py` не запускался: миграций нет.
- Полный backend-регресс, `ruff check .` и `mypy .` не запускались по запрету атомарного шага.

## Не реализовано

- Находки повторного ревью 3–6 не затрагивались: они выделены в следующие атомы и относятся к другой тестовой фикстуре либо frontend.
- Новые роуты, модели, колонки и миграции не добавлялись, потому что атом исправляет загрузку связей внутри существующего сервиса без изменения API и схемы данных.
- Реализация и отчёт не сохранены коммитом из-за запрета записи в служебный Git-каталог worktree.

## Находки

Нет новых находок по данным, утечкам, секретам или персональным данным. Секреты, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.

## Блокеры

Git-сохранение заблокировано правами среды: нельзя создать `index.lock` в `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/`. Реализация остаётся локальной без нового восстанавливаемого commit SHA; `night/volna-9-recovery/JOURNAL.md` не включался в атом как чужое изменение.

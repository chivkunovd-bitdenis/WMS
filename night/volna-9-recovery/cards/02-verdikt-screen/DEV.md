# DEV · 02-verdikt-screen · атом 1

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет; контракт API не менялся.
- Сервис: `_sync_order_meta_from_wb` сохраняет в `metadata_last_checked_at` время старта применённой проверки WB, поэтому результат более позднего запуска побеждает независимо от порядка ответов.
- При ошибке WB fail-closed результат получает тот же маркер времени старта и также не может затереть результат проверки, начатой позже.

## Миграции

Нет.

## Тесты

- `test_fbs_marking_sync_does_not_apply_stale_response` расширен двумя порядками завершения параллельных запросов: старый успех записывается первым и новый отказ записывается первым.
- В варианте `older-persists-first` отдельно доказано промежуточное сохранение старого `filled` без причины и с разрешённой сдачей; после ответа более поздней проверки сохранены `uinBadStatus` и `metadata_delivery_allowed = false`.
- Полностью пройден прямо названный файл `backend/tests/test_fbs_marking.py`: 33 теста.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/app/services/fbs_marking_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend/tests/test_fbs_marking.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/night/volna-9-recovery/cards/02-verdikt-screen/DEV.md`

## Гейты

- Диагностическая попытка до правки: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && .venv/bin/pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_does_not_apply_stale_response` — не запущена: в `backend/` нет `.venv/bin/pytest`.
- Воспроизведение находки новым порядком событий до исправления: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_does_not_apply_stale_response` — `1 failed`; сохранилось ошибочное `metadata_delivery_allowed = true`.
- Целевой тест после исправления и параметризации: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m pytest -q tests/test_fbs_marking.py::test_fbs_marking_sync_does_not_apply_stale_response` — `2 passed in 1.78s`.
- Ruff: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m ruff check app/services/fbs_marking_service.py tests/test_fbs_marking.py` — `All checks passed!`.
- Mypy, обычный целевой запуск: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m mypy app/services/fbs_marking_service.py` — изменённая логика ошибок не дала, но анализ импортов завершился четырьмя существующими ошибками в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; эти файлы вне атома.
- Mypy только файла без анализа импортов: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m mypy --follow-imports=skip app/services/fbs_marking_service.py` — девять существующих `no-any-return` на строках 133, 168–179 и 504, вне изменённых строк.
- Mypy изменённого модуля с отключением только унаследованных `no-any-return`: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m mypy --follow-imports=skip --disable-error-code=no-any-return app/services/fbs_marking_service.py` — `Success: no issues found in 1 source file`.
- Mypy целевого модуля с тихой обработкой импортов: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m mypy --follow-imports=silent app/services/fbs_marking_service.py` — `Success: no issues found in 1 source file`.
- Целевой pytest-файл: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen/backend && python3 -m pytest -q tests/test_fbs_marking.py` — `33 passed in 9.22s`.
- Проверка diff: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && git diff --check` — замечаний нет.
- Сохранение в Git: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-02-verdikt-screen && git add -- backend/app/services/fbs_marking_service.py backend/tests/test_fbs_marking.py night/volna-9-recovery/cards/02-verdikt-screen/DEV.md && git diff --cached --check && git diff --cached --stat && git status --short` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/index.lock`, `Operation not permitted`.
- `back_guard.py` не запускался: атом не добавляет и не меняет роуты.
- `check_migrations.py` не запускался: миграций нет.
- Полный backend-регресс, `ruff check .` и `mypy .` не запускались по запрету атомарного шага.

## Не реализовано

- Находка ревью про `populate_existing=True` и `MissingGreenlet` не исправлялась: она выделена в атом 2 и требует изменений сценариев замены ЧЗ из `backend/tests/test_fbs_kiz.py`.
- Ошибочная фикстура успеха WB из атома 3 и frontend-находки 4–6 не затрагивались.
- Новые роуты, модели, колонки и миграции не добавлялись, потому что этот атом является серверной защитой существующих данных без изменения API.
- Реализация и отчёт не сохранены коммитом: среда запретила запись в служебный Git-каталог зарегистрированного worktree.

## Находки

Нет новых находок по данным, утечкам, секретам или персональным данным. Секреты, токены, `.env`, кабинеты учётных данных, живой Wildberries и production `194.87.96.144` не читались и не затрагивались.

## Блокеры

Git-сохранение заблокировано правами среды: нельзя создать `index.lock` в `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-02-verdikt-screen1/`. Реализация остаётся локальной без восстанавливаемого commit SHA.

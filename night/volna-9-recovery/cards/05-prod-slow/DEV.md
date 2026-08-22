# Backend dev · 05-prod-slow · атом 4 · rework

## Что реализовано

- `POST /operations/marking-codes/label-artifact-tape` — контракт `202`/job сохранён; одинаковый запрос переиспользует активное или готовое задание, пока его `label_tape` доступен.
- `marking_code_service.build_label_artifact_tape_pdf` — этикетки читаются из БД и передаются сборщику последовательно, без списка из 500 исходных BLOB.
- `marking_label_artifact_service.merge_label_artifact_pdfs_for_print_stream` — добавляет в итоговый PyMuPDF-документ по одному исходному PDF; при заданном формате страницы преобразованная копия также не накапливается в отдельном списке.
- `celery_app` — сборка ленты и удаление истёкшего бинарного файла направлены в одну очередь `print`.
- `docker-compose.prod.yml` — API и единственный `print_worker` используют общий именованный том `wms_data` по пути `/var/lib/wms`, поэтому сохранённый worker PDF доступен API, а уборщик видит тот же файл.
- `background_job_service` — проверено уже присутствующее исправление ревью: готовый job переиспользуется до истечения asset, а уборка очищает только `storage_path`, сохраняя строку `FbsPrintAsset` и ссылку job для аудита.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/marking_code_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/marking_label_artifact_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/celery_app.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_marking_pdf_label_artifact.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/docker-compose.prod.yml`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

## Миграции

Нет.

## Тесты

- `test_streaming_tape_merge_consumes_one_source_at_a_time` — доказывает, что следующий исходный PDF не запрашивается до добавления предыдущего в итоговый документ; проверено 155 страниц.
- `test_label_tape_load_does_not_block_health[155]` и `[500]` — параллельно со сборкой в изолированном worker-thread опрашивают `/health`, проверяют число страниц и фиксируют длительность.
- `test_label_tape_and_expiry_cleanup_share_print_queue` — сборка и уборка закреплены за очередью `print`.
- Целевой регрессионный набор также проверяет `202`, повтор того же pending/done job, ровно один asset, перевод job в `failed` и недоступность истёкшего asset при сохранённой аудиторской строке.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && ruff check app/services/marking_code_service.py app/services/marking_label_artifact_service.py app/celery_app.py tests/test_marking_pdf_label_artifact.py tests/test_background_jobs.py` — PASS, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy app/services/marking_code_service.py app/services/marking_label_artifact_service.py app/services/background_job_service.py app/tasks/background_jobs.py app/celery_app.py` — FAIL только на 4 ранее существующих ошибках импортируемых зависимостей: `wildberries_credentials_service.py:167`, `fbs_stock_sync_service.py:617`, `fbs_warehouse_binding_service.py:23,291`; в файлах атома ошибок не выдано.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy --follow-imports=skip app/services/marking_code_service.py app/services/marking_label_artifact_service.py app/celery_app.py` — PASS, `Success: no issues found in 3 source files`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q tests/test_marking_codes.py tests/test_marking_pdf_label_artifact.py tests/test_background_jobs.py tests/test_fbs_print_assets.py` — PASS, `44 passed, 5 warnings in 26.39s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q -s tests/test_marking_pdf_label_artifact.py::test_streaming_tape_merge_consumes_one_source_at_a_time tests/test_marking_pdf_label_artifact.py::test_label_tape_load_does_not_block_health` — PASS, `3 passed`; 155 этикеток: job `0.084 s`, max `/health` `0.024 s`; 500 этикеток: job `0.275 s`, max `/health` `0.000 s`.
- Без чтения `.env` выполнен `yaml.safe_load` файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/docker-compose.prod.yml` с утверждениями общего `WMS_DATA_DIR`, mount `wms_data:/var/lib/wms` у API/print-worker и объявления volume — PASS.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git diff --check` — PASS.
- `python3 scripts/ci/back_guard.py` не запускался: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` не запускался: миграция не добавлялась.
- `git add backend/app/celery_app.py backend/app/services/marking_code_service.py backend/app/services/marking_label_artifact_service.py backend/tests/test_background_jobs.py backend/tests/test_marking_pdf_label_artifact.py docker-compose.prod.yml night/volna-9-recovery/cards/05-prod-slow/DEV.md && git commit -m "fix(marking): stream queued label tape assets"` — BLOCKED средой до изменения индекса: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock`, `Operation not permitted`.

## Не реализовано

- Находки ревью №1 и №8–10 относятся к frontend/screen-dev, а №3–4 — к соседним атомам WB-sync; согласно роли `backend-dev` и границе атома 4 эти файлы не менялись.
- Реальный отдельный Celery-стенд не поднимался и production не затрагивался. Нагрузочный сценарий 155/500 выполнен локально с изоляцией сборщика от ASGI event loop и параллельным `/health`; инфраструктурный замер RSS отдельного контейнера остаётся стендовой проверкой.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Реализация и тесты находятся в постоянной рабочей копии, но новый commit SHA создать невозможно из-за запрета среды на запись в служебный Git-каталог зарегистрированного worktree. Изменения локально реализованы, но не сохранены отдельным коммитом и не опубликованы.

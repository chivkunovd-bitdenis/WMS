# Backend dev · 05-prod-slow · атом 4 · rework по REVIEW.md

## Что реализовано

- `background_job_service.run_marking_label_tape_job` — для активной сборки ленты ЧЗ добавлен heartbeat раз в 60 секунд: он продлевает 15-минутный lease только при совпадении предыдущей отметки владельца, поэтому повторная доставка того же Celery-задания не запускает параллельную сборку и не создаёт второй `label_tape` asset.
- `_refresh_marking_label_tape_lease` / `_maintain_marking_label_tape_lease` — heartbeat работает через отдельную короткую сессию БД; ошибка обновления или потеря lease переводит текущую сборку в безопасную ошибку `marking_label_tape_lease_lost` до публикации asset.
- Существующий `POST /operations/marking-codes/label-artifact-tape` не менялся: по-прежнему отвечает `202`, возвращает `job_id` и переиспользует тот же активный job.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/background_job_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

## Миграции

Нет.

## Тесты

- `test_marking_label_tape_heartbeat_prevents_duplicate_worker_and_asset` — искусственно сокращает lease до 80 мс, держит первую сборку дольше lease, запускает повторный worker и подтверждает один вызов сборщика, статус `done` и ровно один asset.
- Целевой набор атома повторно проверяет `202`, повторное использование pending/running/done job, один готовый asset, `failed` при ошибке, недоступность истёкшего asset и сохранность аудиторской строки.
- Нагрузочные параметры 155 и 500 этикеток повторно проверены параллельно с `/health`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && ruff check app/services/background_job_service.py tests/test_background_jobs.py` — PASS, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy app/services/background_job_service.py` — FAIL только на 4 ранее существующих ошибках импортируемых соседних модулей: `wildberries_credentials_service.py:167`, `fbs_stock_sync_service.py:617`, `fbs_warehouse_binding_service.py:23,291`; в изменённом модуле ошибок нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy --follow-imports=skip app/services/background_job_service.py` — PASS, `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q tests/test_background_jobs.py::test_marking_label_tape_worker_does_not_reclaim_fresh_running_job tests/test_background_jobs.py::test_marking_label_tape_worker_reclaims_stale_running_job tests/test_background_jobs.py::test_marking_label_tape_heartbeat_prevents_duplicate_worker_and_asset` — PASS, `3 passed in 2.87s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q tests/test_marking_codes.py tests/test_marking_pdf_label_artifact.py tests/test_background_jobs.py tests/test_fbs_print_assets.py` — PASS, `45 passed, 5 warnings in 27.24s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q -s tests/test_marking_pdf_label_artifact.py::test_label_tape_load_does_not_block_health` — PASS, `2 passed`; 155 этикеток: job `0.082 s`, max `/health` `0.023 s`; 500 этикеток: job `0.265 s`, max `/health` `0.000 s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git diff --check` — PASS.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git add backend/app/services/background_job_service.py backend/tests/test_background_jobs.py night/volna-9-recovery/cards/05-prod-slow/DEV.md && git commit -m "fix(marking): keep label tape lease alive"` — BLOCKED до изменения индекса: среда запретила создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` (`Operation not permitted`).
- `python3 scripts/ci/back_guard.py` не запускался: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` не запускался: миграция не добавлялась.

## Не реализовано

- Находка ревью №1 относится к атомам WB-sync (`fbs_autopoll_service.py`, `wb_marketplace_orders_service.py`), находки №3–5 — к frontend, находка №6 — к документации блокеров. В рамках роли `backend-dev` и атома 4 эти файлы не менялись.
- API-контракт, PDF-сборщик и инфраструктура очереди не переписывались: текущий rework адресно исправляет единственную относящуюся к этому слою находку №2.
- Боевой production и живой кабинет Wildberries не затрагивались.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.

## Блокеры

- Код, тест и артефакт находятся в постоянной зарегистрированной рабочей копии, но отдельный commit SHA создать невозможно из-за запрета среды на запись в служебный Git-каталог worktree. Изменения локально реализованы и проверены, но не сохранены отдельным коммитом и не опубликованы.

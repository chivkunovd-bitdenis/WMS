# DEV · 05-prod-slow · backend-dev

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/api/marking_codes.py — повторный активный job больше не публикуется повторно.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/background_job_service.py — атомарный захват pending-job и плановая очистка истёкших `label_tape` assets.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/tasks/background_jobs.py — Celery-задача очистки.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/celery_app.py — маршрут `marking_label_tape` в очередь `print` и hourly cleanup в beat.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/docker-compose.prod.yml — production worker слушает `celery,print`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py — регрессия идемпотентной публикации pending-job.

## Миграции

нет — схема базы данных не менялась.

## Гейты

- ruff: targeted files — PASS; полный `ruff check .` — FAIL на существующих несвязанных нарушениях в рабочей копии.
- mypy: FAIL на существующих несвязанных ошибках в `wildberries_credentials_service.py` и `fbs_stock_sync_service.py`; изменённые файлы не добавили диагностик.
- pytest: `backend/tests/test_background_jobs.py` — 5 passed.
- back_guard.py: не запущен — файл отсутствует в этой рабочей копии (`scripts/ci/back_guard.py` не найден).
- check_migrations.py: не запущен — файл отсутствует в этой рабочей копии (`scripts/ci/check_migrations.py` не найден).

## Не реализовано

- Frontend-состояния и Playwright-сценарии не менялись: они относятся к другой роли.
- Находки ревью по WB-autopoll и frontend не относятся к этому backend-атому и не затрагивались.
- Нагрузочный прогон 155/500 кодов с `/health` не выполнялся в рамках локального backend-теста.

## Блокеры

Нет блокеров по реализации. Полные общие ruff/mypy и два repository guard-скрипта ограничены состоянием/составом этой рабочей копии, указанным выше.

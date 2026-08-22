## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/background_job_service.py — конкурентно безопасное создание активной job по ключу идемпотентности и атомарный захват `marking_label_tape`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_print_asset_storage.py — удаление одного валидированного файла после истечения срока.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_print_asset_service.py — удаление PDF ленты при отказе после 12 часов.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py — проверки состояний job, результата только с `asset_id` и повторной доставки running job.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_fbs_print_assets.py — ruff-форматирование импортов существующих тестов истечения срока.

## Миграции

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/alembic/versions/20260822_0050_marking_label_tape_jobs.py` уже содержит добавляющую миграцию `idempotency_key`, активный уникальный индекс и `expires_at`; новая миграция не добавлялась.

## Тесты

- Целевой прогон `tests/test_background_jobs.py tests/test_fbs_print_assets.py`: 12 passed.
- Полный `pytest`: остановлен после зависания прогона примерно на 38%; до остановки обнаружены падения в существующих сценариях `test_fbs_orders_intake.py` и `test_fbs_stock_emulator_integration.py`, не связанных с этим атомом.

## Гейты

- `ruff check .` — FAIL: 80 существующих нарушений в несвязанных файлах; целевые изменённые файлы проходят.
- `mypy .` — FAIL: существующие ошибки в 7 файлах; после исправления типы изменённых файлов проходят, остаются ошибки соседних модулей и старых тестов.
- `pytest` — STOPPED после зависания полного прогона; целевые тесты зелёные, полный прогон выявил несвязанные падения.
- `python3 scripts/ci/back_guard.py` — BLOCKED: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — BLOCKED: файл отсутствует в рабочей копии.

## Не реализовано

- Очередь Celery и production-worker из находки 1 не менялись: это инфраструктурная граница данного backend-атома.
- Периодическая уборка всех истёкших файлов не добавлялась; реализована безопасная уборка конкретного PDF при попытке выдачи после истечения срока.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.
- Commit — BLOCKED: Git не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` (`Operation not permitted`); изменения не сохранены в commit.

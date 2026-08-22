## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/models/background_job.py — добавлены тип задания `marking_label_tape`, ключ идемпотентности и уникальность активного запроса.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/models/fbs_print_asset.py — добавлены вид `label_tape` и срок доступности артефакта.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/background_job_service.py — повтор активного запроса возвращает существующее задание.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_print_asset_service.py — истёкший артефакт не выдаётся.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/alembic/versions/20260822_0050_marking_label_tape_jobs.py — добавляющая миграция.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py — идемпотентность и ссылка `asset_id`.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_fbs_print_assets.py — отказ после истечения срока.

## Гейты

- ruff — targeted изменённые файлы: PASS; полный `ruff check .`: FAIL на существующих несвязанных ошибках репозитория (84 ошибки, включая старые `noqa` и ошибки в других модулях).
- mypy — не выполнен полным проходом после остановки цепочки на полном ruff; targeted запуск требует повторного запуска из `backend/`.
- pytest — PASS: 10 тестов в `tests/test_background_jobs.py tests/test_fbs_print_assets.py`.
- back_guard.py — не выполнен: файл `scripts/ci/back_guard.py` отсутствует в этой рабочей копии.
- check_migrations.py — не выполнен: файл `scripts/ci/check_migrations.py` отсутствует в этой рабочей копии.
- Git commit — не выполнен: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` из-за ограничения доступа; изменения остаются в рабочем дереве.

## Не реализовано

- API-эндпоинт постановки и worker сборки PDF не входят в этот атомарный кусок; контрактом этой карточки заданы только серверные сущности, идемпотентность и срок выдачи артефакта.
- Поле истечения не удаляет бинарный файл автоматически; уборка должна выполняться отдельным worker-контуром.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не затрагивались.

# Backend dev · 05-prod-slow · атом 3 · переделка по ревью

## Что реализовано

- Эндпоинты: новых и изменённых роутов нет; существующий запрос фоновой ленты получает исправленную семантику через сервис заданий.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/background_job_service.py`: одинаковый `marking_label_tape` возвращает тот же `done`-job, пока связанный PDF доступен; `pending/running` по-прежнему single-flight, `failed` допускает новый запуск, а истёкший или недоступный артефакт освобождает ключ для повторной сборки.
- Сервис очистки: после 12 часов удаляется только PDF и обнуляется `storage_path`; строка `FbsPrintAsset`, контрольная сумма и ссылка `BackgroundJob.result_json.asset_id` сохраняются для аудита.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/models/background_job.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/background_job_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/alembic/versions/20260822_0050_marking_label_tape_jobs.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

## Миграции

- `20260822_0050`: добавляющая миграция по-прежнему добавляет `background_jobs.idempotency_key` и `fbs_print_assets.expires_at`; частичный уникальный индекс переименован в `uq_background_jobs_reusable_idempotency` и охватывает `pending/running` для всех job, а `done` — только для `marking_label_tape`.

## Тесты

- `test_done_marking_job_is_reused_while_asset_is_available`: готовый доступный PDF возвращает тот же job и повторно не публикуется.
- `test_failed_marking_job_can_be_retried_with_same_idempotency_key`: ошибочный job не блокирует повтор.
- `test_expired_tape_cleanup_retains_audit_row_and_releases_request_key`: уборка удаляет бинарный файл один раз, сохраняет asset и `asset_id`, после чего тот же запрос может создать новый job.
- Сохранены прежние проверки состояний `pending/running/done/failed`, single-flight активного запроса, восстановления stale `running`, отсутствия PDF в `result_json` и отказа в выдаче после 12 часов.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && ruff check app/models/background_job.py app/models/fbs_print_asset.py app/services/background_job_service.py alembic/versions/20260822_0050_marking_label_tape_jobs.py tests/test_background_jobs.py tests/test_fbs_print_assets.py` — пройдено: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy app/models/background_job.py app/models/fbs_print_asset.py app/services/background_job_service.py` — целевые модули проверены, но общий граф импортов дал 4 ранее существующие ошибки вне атома: `wildberries_credentials_service.py:167`, `fbs_stock_sync_service.py:617`, `fbs_warehouse_binding_service.py:23,291`; ошибок в изменённых файлах нет.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q tests/test_background_jobs.py tests/test_fbs_print_assets.py` — пройдено: `18 passed in 13.10s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && alembic heads` — пройдено: единственная голова `20260822_0050 (head)`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && python3 scripts/ci/check_migrations.py` — не запущено по существу: скрипт отсутствует в этой рабочей копии; прямой вызов завершился с `No such file or directory`.
- `back_guard.py` — неприменим: атом не добавляет и не изменяет роут; скрипт также отсутствует в рабочей копии.
- `git diff --check` — пройдено.

## Не реализовано

- Находки ревью №1–5 и №8–10 относятся к frontend, infra или другим backend-атомам и не входят в файлы и слой атома 3.
- Находки №6 и №7, относящиеся к серверному контракту этого атома, исправлены полностью.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/models/fbs_print_asset.py` не менялся: уже имеющихся nullable-поля `storage_path` и `expires_at` достаточно для сохранения аудита без бинарного содержимого.
- Секреты, ключи, токены, `.env`, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Блокеров реализации нет. Целевой `mypy` остаётся ненулевым только из-за четырёх диагностик в чужих модулях, перечисленных в разделе «Гейты».
- Сохранение в Git заблокировано ограничением файловой системы среды: `git add ... && git commit ...` не может создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock` и завершается `Operation not permitted`. Изменения и этот артефакт остаются в рабочем дереве без нового commit SHA.

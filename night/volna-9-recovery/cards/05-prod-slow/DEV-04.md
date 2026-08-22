# Backend dev · 05-prod-slow · атом 4

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/api/marking_codes.py` — публикация существующего `marking_label_tape` job в очередь `print` стала best-effort: отказ брокера не меняет ответ `202`, а durable `pending` job повторно публикуется тем же идемпотентным запросом.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py` — регрессия отказа публикации в брокер: API-обвязка не выбрасывает ошибку и активное задание остаётся пригодным для повторной публикации.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — отчёт backend-dev.

## Что реализовано

- `POST /operations/marking-codes/label-artifact-tape` — после сохранения job возвращает `202` даже при временном отказе Celery-брокера; повтор того же запроса использует тот же активный job, без дубликата.
- `background_job_service` — действующее восстановление stale `running` job после 15-минутной аренды и single-flight захват job сохранены; worker создаёт один `label_tape` asset, ошибки переводят job в `failed`.

## Миграции

- Нет новых миграций. Используется существующая добавляющая `20260822_0050_marking_label_tape_jobs.py` с идемпотентным ключом, частичным уникальным индексом активного job и сроком хранения asset.

## Гейты

- `ruff check .` — FAIL: 79 существующих нарушений вне атома; адресный `ruff check` файлов атома — PASS.
- `mypy .` — FAIL: 21 существующая ошибка в 6 несвязанных файлах; адресный запуск слоя очереди видит 4 ошибки из зависимостей вне атома, новых ошибок в изменённых файлах нет.
- `pytest tests/test_background_jobs.py tests/test_marking_pdf_label_artifact.py tests/test_fbs_print_assets.py` — PASS, 34 passed; покрыты `202`, тот же active job, один PDF asset, ошибка worker и истечение asset.
- `pytest` — FAIL вне атома: после 161 passed и 3 skipped остановлен на 11 падениях в `tests/test_fbs_orders_intake.py`, связанных с WB-статусами и поставками; сценарии ленты ЧЗ не затронуты и адресный набор из 34 тестов зелёный.
- `python3 scripts/ci/back_guard.py` — не запущен: файла нет в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — не запущен: файла нет в этой рабочей копии.
- `git diff --check` — PASS.

## Не реализовано

- Нагрузочный прогон на 155 и 500 кодов с одновременным `/health` не запускался: для него требуется выделенный стенд с Celery worker; production не затрагивался.
- Фронтенд-находки ревью №1, №4–10 не относятся к backend-слою этого атома и не изменялись.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

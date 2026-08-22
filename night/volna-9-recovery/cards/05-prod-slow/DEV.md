# Backend dev · 05-prod-slow · атом 3

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/background_job_service.py` — повторная публикация активного `marking_label_tape` и восстановление только устаревшего `running`-job после 15-минутной аренды; захват остаётся single-flight на уровне БД.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/api/marking_codes.py` — повторный идентичный запрос публикует тот же активный job, не создавая дубликат.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/alembic/versions/20260822_0050_marking_label_tape_jobs.py` — отформатирована существующая добавляющая миграция: `idempotency_key`, частичный уникальный индекс активного job и `expires_at` для print asset.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py` — сценарии повторной публикации без второго job, запрета захвата свежего `running` и восстановления устаревшего `running`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — отчёт backend-dev.

## Гейты

- `ruff check .` — не пройден: 79 уже существующих ошибок вне изменённого атома. Адресный `ruff check` всех файлов атома — пройден.
- `mypy .` — не пройден: 21 уже существующая ошибка в шести чужих файлах. Адресный запуск также видит старые ошибки зависимостей и тестовых фикстур; новых диагностик в изменённом сервисе и API нет.
- `pytest tests/test_background_jobs.py tests/test_fbs_print_assets.py` — пройдено: 16 passed.
- `pytest` — полный набор не завершился в изолированной среде запуска до выдачи результата; адресные наборы атома прошли: 16 passed.
- `python3 scripts/ci/back_guard.py` — не запущен: файла нет в этой рабочей копии.
- `python3 scripts/ci/check_migrations.py` — не запущен: файла нет в этой рабочей копии.
- `git diff --check` — пройден.

## Не реализовано

- Фронтенд-находки ревью №1, №4–10 не относятся к серверному атому 3 и его файлам; они не изменялись.
- Серверная находка ревью №2 исправлена: повтор активного запроса повторно ставит в очередь тот же job, а stale `running` можно безопасно перехватить; свежий `running` не перехватывается.
- Секреты, ключи, токены, `.env`, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

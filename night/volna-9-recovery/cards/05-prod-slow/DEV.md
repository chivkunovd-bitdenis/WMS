# Backend-dev отчёт · 05-prod-slow

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/docker-compose.prod.yml` — очередь `print` отделена от обычного Celery worker; добавлен отдельный `print_worker` с `--concurrency=1`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_background_jobs.py` — регрессия повторного запуска с тем же ключом после `failed` и `done`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_fbs_stock_emulator_integration.py` — проверка разделения очередей в production compose.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — этот отчёт.

## Что реализовано

- Production запускает обычные задачи только в очереди `celery`, а печать лент — в отдельном worker очереди `print` с одним процессом; две тяжёлые ленты не собираются параллельно.
- Условный уникальный индекс активных print-job уже поддерживает PostgreSQL и SQLite; тест теперь проверяет повтор после обоих финальных статусов (`failed` и `done`).

## Миграции

- Нет новых миграций. Используется существующая `20260822_0050`, которая добавляет `idempotency_key`, частичный индекс активных job для PostgreSQL и SQLite и `fbs_print_assets.expires_at`.

## Гейты

- `ruff check .` — FAIL: 80 существующих нарушений в несвязанных файлах; изменённые backend-тесты проверены отдельно и ошибок не имеют.
- `mypy .` — FAIL: 21 существующая ошибка в 6 несвязанных файлах; изменённые файлы не добавили ошибок.
- `pytest` — целевые тесты фоновых print-job прошли; полный прогон в этой среде не завершил вывод после старта набора.
- `python3 scripts/ci/back_guard.py` — не запущен: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — не запущен: файл отсутствует в рабочей копии.
- `git diff --check` — PASS.

## Не реализовано

- Frontend polling, закрытие диалога, popup/fallback и E2E-сценарии не менялись: это не backend-dev слой данного атома.
- Нагрузочный прогон на 155/500 кодов и `/health` не запускался: для него нужен стенд с брокером и worker; production не затрагивался.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

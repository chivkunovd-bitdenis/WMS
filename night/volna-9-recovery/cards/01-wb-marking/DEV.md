# DEV · 01-wb-marking · backend-dev · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py` — batch DTO сохраняет `decision`, `value`, `reason`; первый ответ `429` ожидает числовой `Retry-After` и повторяет ту же пачку ровно один раз.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py` — проверки полного `metaDetails`, единственного повтора `429`, ошибок `4xx/5xx` и неразбираемого ответа.

## Миграции

Нет.

## Тесты

- `test_fetch_orders_meta_batch_exact_contract_and_parse` проверяет сохранение `decision`, `value`, `reason`.
- `test_fetch_orders_meta_batch_retries_429_once_after_retry_after` проверяет ровно два запроса и ожидание `Retry-After`.
- Проверки ошибок подтверждают, что неуспешный или неразбираемый ответ не превращается в DTO-успех.

## Гейты

- `ruff check .` — FAIL: в полном backend есть ранее существующие ошибки в несвязанных файлах; целевые файлы проходят (`All checks passed`).
- `mypy .` — FAIL/не пройден в полном backend из-за ранее существующих ошибок; целевой `app/services/wildberries_fbs_client.py` проходит (`Success: no issues found`).
- `pytest` — релевантный набор PASS: 17 passed; полный suite не запускался.
- `python3 scripts/ci/back_guard.py` — недоступен: файл отсутствует в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — недоступен: файл отсутствует в рабочей копии; миграций нет.

## Не реализовано

- Остальные атомы карточки не затрагивались: `wb_orphaned`, применение ответа к локальной привязке, автополлер пачек и удаление устаревшего одиночного чтения.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.

# DEV · 01-wb-marking · атом 1/5 · rework после JUDGE

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py`: рабочее batch-чтение `POST /api/marketplace/v3/orders/meta` возвращает DTO с `decision`, `value` и `reason`; при первом `429` ждёт значение `Retry-After` и ровно один раз повторяет ту же пачку не более чем из 100 заказов; остальные `4xx/5xx` и неразбираемое тело завершаются `WildberriesClientError`, а не частичным успехом.
- Реализация и тесты атома уже сохранены в истории текущей ветки коммитом `8e8f2a3e9908956550eb8cb3278ec137d404f8ba`. Повторная проверка `JUDGE.md` не выявила замечаний в backend-файлах или слое этого атома, поэтому необоснованный кодовый diff не создавался.

## Миграции

- Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py::test_fetch_orders_meta_batch_exact_contract_and_parse` проверяет сохранение `decision`, `value` и `reason` в DTO.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py::test_fetch_orders_meta_batch_retries_429_once_after_retry_after` проверяет ожидание `Retry-After`, ровно один повтор и успешный результат повторённой пачки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py::test_fetch_orders_meta_batch_honors_retry_after_http_date` проверяет HTTP-date форму `Retry-After`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py::test_fetch_orders_meta_batch_does_not_retry_other_errors` проверяет ошибку без повтора для `400` и `500`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py::test_fetch_orders_meta_batch_rejects_malformed_response_after_single_429_retry` проверяет, что неразбираемое тело после единственного повтора возвращает `invalid_response`, а не частичный успех.
- Полностью выполнен разрешённый тестовый файл атома: 19 тестов прошли.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — восстановлен обязательный отчёт текущего атома после удаления внешним оркестратором.

Backend-файлы в текущем rework не изменялись: они уже буквально соответствуют атому, а единственная находка `JUDGE.md` относится к отсутствующему живому браузерному стенду, не к backend-слою.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/wildberries_fbs_client.py tests/test_wildberries_marketplace_fbs_client.py` — PASS: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/wildberries_fbs_client.py` — PASS: `Success: no issues found in 1 source file`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_wildberries_marketplace_fbs_client.py` — PASS: `19 passed in 0.06s`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — не запускался: атом не добавляет и не меняет роуты.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — не запускался: атом не добавляет миграцию.

## Не реализовано

- Единственная находка `JUDGE.md` — неподнятый живой UI-стенд и отсутствие браузерных снимков зон `S-03`, `S-14`, `S-15`. Она не относится к разрешённым backend-файлам и слою атома 1, поэтому backend-изменений для неё нет.
- Расписание, UI, модели, миграции, новые роуты и обращения к живому кабинету Wildberries не менялись.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Нет для backend-атома. Браузерная продуктовая проверка остаётся отдельным этапом согласно `JUDGE.md`.

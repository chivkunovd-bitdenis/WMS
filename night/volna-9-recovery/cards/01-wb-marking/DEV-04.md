# DEV · 01-wb-marking · атом 4 · rework

## Что реализовано

- Эндпоинты: нет.
- Сервис `sync_marking_statuses_for_assembling_supplies`: подтверждена последовательная обработка уникальных `wb_order_id` пачками не более 100, применение ответа по `order_id`, перевод пропущенного в успешной пачке заказа в безопасный `unknown` без свежего времени проверки и продолжение после локализованной ошибки пачки.
- Сервис `_sync_order_meta_from_wb`: подтверждено, что любое отличающееся заполненное значение WB, включая решение `invalid`, даёт `replacement_required`, не освобождает локальный КИЗ и сохраняет аудит `wb_orphaned`.
- Сервис `fetch_marketplace_orders_meta_batch`: подтверждено, что встроенный mock возвращает рабочий `metaDetails`, а единственный повтор после 429 соблюдает числовой `Retry-After` и HTTP-дату без искусственного ограничения одной секундой.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py` — исправление применения пропущенного `order_id` уже сохранено в текущей ветке.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py` — безопасный `unknown` и общее правило расхождения заполненных значений уже сохранены в текущей ветке.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/wildberries_fbs_client.py` — рабочий mock `metaDetails` и корректный `Retry-After` уже сохранены в текущей ветке.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py` — пакетная последовательность, частичный ответ и продолжение после ошибки уже покрыты в текущей ветке.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_kiz.py` — частичный ответ и `invalid` с чужим КИЗ уже покрыты в текущей ветке.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_wildberries_marketplace_fbs_client.py` — mock batch-контракт и обе формы `Retry-After` уже покрыты в текущей ветке.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — обновлённый отчёт rework по атому 4.

## Миграции

- Нет.

## Тесты

- `test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches`: 201 заказ обрабатывается последовательными пачками `100/100/1`; строки сопоставляются по `order_id`; пропущенный заказ становится `unknown`; ошибка средней пачки не меняет её локальные данные и не останавливает последнюю пачку.
- `test_fbs_marking_sync_updates_check_status`: существующий ручной путь одного заказа остаётся допустимой пачкой из одного ID.
- `test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail`: среди параметров проверен `invalid` с отличающимся заполненным значением, результат — `replacement_required`.
- `test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time`: неполный ответ сбрасывает прежний положительный статус в `unknown`, не проставляя свежую дату успешной проверки.
- `test_fetch_orders_meta_batch_mock_returns_meta_details`: встроенная заглушка возвращает данные в `metaDetails`, а не в устаревшем `row.meta`.
- `test_fetch_orders_meta_batch_retries_429_once_after_retry_after` и `test_fetch_orders_meta_batch_honors_retry_after_http_date`: повтор после 429 ждёт переданное число секунд или интервал до HTTP-даты.

## Гейты

- `pytest -q tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status tests/test_fbs_kiz.py::test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail tests/test_fbs_kiz.py::test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time tests/test_wildberries_marketplace_fbs_client.py::test_fetch_orders_meta_batch_retries_429_once_after_retry_after tests/test_wildberries_marketplace_fbs_client.py::test_fetch_orders_meta_batch_honors_retry_after_http_date tests/test_wildberries_marketplace_fbs_client.py::test_fetch_orders_meta_batch_mock_returns_meta_details` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `15 passed in 9.81s`.
- `ruff check app/services/fbs_marking_service.py app/services/fbs_autopoll_service.py app/services/wildberries_fbs_client.py tests/test_fbs_marking.py tests/test_fbs_kiz.py tests/test_wildberries_marketplace_fbs_client.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `All checks passed!`.
- `mypy app/services/fbs_marking_service.py app/services/fbs_autopoll_service.py app/services/wildberries_fbs_client.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — в трёх целевых модулях ошибок нет; команда завершилась кодом 1 из-за четырёх существующих ошибок в импортируемых соседних файлах `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`.
- `python3 scripts/ci/back_guard.py` — неприменим: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` — неприменим: миграция не добавлялась.
- `git diff --check -- night/volna-9-recovery/cards/01-wb-marking/DEV.md` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking` — пройдено.
- `git add -- night/volna-9-recovery/cards/01-wb-marking/DEV.md && git diff --cached --check && git commit -m "docs(wb-marking): record atom 4 rework validation"` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking` — не выполнено ограниченной средой: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock` (`Operation not permitted`).

## Не реализовано

- Нет. Все четыре относящиеся к backend-слою находки `REVIEW.md` исправлены в текущей ветке и подтверждены адресными тестами; соседние продуктовые задачи не затрагивались.

## Находки

- Формального раздела «API и данные» в `CONTRACT.md` нет; работа выполнена по явно заданному backend-атому 4 из `FEATURES.md` и обязательному rework-вердикту `REVIEW.md`.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Backend-реализация находок уже сохранена в текущей ветке на `ce46191f` и предшествующих атомарных коммитах, но обновлённый обязательный `DEV.md` остаётся незакоммиченным: песочница разрешает запись в рабочую копию, но запрещает запись в Git-метаданные зарегистрированного worktree за её пределами. Для сохранения отчёта нужен повтор указанной в «Гейтах» команды процессом с доступом к `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/`.

# DEV · 01-wb-marking · атом 4 · rework

## Что реализовано

- Эндпоинты: нет.
- Сервис `sync_marking_statuses_for_assembling_supplies`: подтверждена существующая последовательная обработка уникальных `wb_order_id` пачками `100/100/1`, применение ответа по `order_id` и продолжение после локализованной ошибки пачки.
- Сервис `_sync_order_meta_from_wb`: адресными тестами подтверждены исправления четырёх находок ревью — сохранение полного удалённого снимка, контрактное отображение `check_status`, отказ от legacy `row.meta` и однократный аудит при конкурентном запуске.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py` — batch-тест дополнен явной проверкой последовательности запросов и сохранности локальных данных ошибочной пачки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md` — отчёт текущего backend-атома.

## Миграции

- Нет.

## Тесты

- Усилен `test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches`: 201 заказ разбивается на последовательные уникальные пачки `100/100/1`; первая пачка возвращается в обратном порядке и без одной строки, средняя падает, последняя всё равно выполняется; максимум одновременно активен один batch-запрос; 100 локальных маркировок ошибочной пачки остаются в прежних статусах.
- Повторно проверены параметризованные решения WB, неизвестный ключ `metaDetails`, отсутствие ожидаемого `kind`, полный удалённый снимок и конкурентный плюс повторный запуск `wb_orphaned`.
- Проверен существующий ручной путь одного заказа через `test_fbs_marking_sync_updates_check_status`: один ID остаётся допустимой пачкой.

## Гейты

- `ruff check tests/test_fbs_marking.py app/services/fbs_marking_service.py app/services/fbs_autopoll_service.py tests/test_fbs_kiz.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `All checks passed!`.
- `mypy app/services/fbs_marking_service.py app/services/fbs_autopoll_service.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — целевые модули проверены, общий код возврата 1 из-за четырёх уже существующих ошибок в импортируемых соседних файлах `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; ошибок в двух названных целевых модулях вывод не содержит.
- `pytest -q tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status tests/test_fbs_kiz.py::test_fbs_marking_wb_meta_decision_is_safe_and_preserves_raw_detail tests/test_fbs_kiz.py::test_fbs_marking_partial_wb_row_is_unknown_without_fresh_check_time tests/test_fbs_kiz.py::test_fbs_marking_orphaned_audit_is_created_once_for_concurrent_and_repeated_missing` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend` — пройдено: `13 passed in 49.31s`.
- `python3 scripts/ci/back_guard.py` — неприменим: новый роут не добавлялся.
- `python3 scripts/ci/check_migrations.py` — неприменим: миграция не добавлялась.
- `git diff --check` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking` — пройдено.
- `git add -- backend/tests/test_fbs_marking.py night/volna-9-recovery/cards/01-wb-marking/DEV.md && git commit -m "test(wb-marking): prove sequential batch recovery"` — не выполнено ограниченной средой: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/index.lock` (`Operation not permitted`).

## Не реализовано

- Нет. Рабочая логика атома и исправления находок ревью уже присутствовали в ветке; текущий rework усилил недостающие доказательства последовательности и сохранности данных на ошибке пачки.

## Находки

- Формального раздела «API и данные» в `CONTRACT.md` нет; реализация продолжена по отдельному разрешению владельца ночной волны и однозначным backend-правилам в `FEATURES.md`, `ARCH.md` и `REVIEW.md`.
- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Изменения локально реализованы и проверены, но не сохранены коммитом: служебный Git-каталог зарегистрированного worktree доступен этой среде только для чтения. Для сохранения нужен повтор `git add` и `git commit` процессом с правом записи в `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-01-wb-marking1/`.

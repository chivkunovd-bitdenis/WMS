# DEV · 01-wb-marking · атом 4 · rework

## Что реализовано

- Эндпоинты: нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_autopoll_service.py`: активные собираемые поставки сверяются последовательными пачками до 100 уникальных `wb_order_id`; после ошибки одной пачки следующая продолжает работу, а ответ применяется по `order_id`, а не по позиции.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/app/services/fbs_marking_service.py`: ручной путь с одним заказом остаётся допустимой пачкой; пропущенная строка WB не засчитывается как успешная сверка.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/night/volna-9-recovery/cards/01-wb-marking/DEV.md`

Код атома уже находится в текущем `HEAD`; по находке из `JUDGE.md` изменений backend-кода не требуется: вердикт фиксирует только отсутствие живого браузерного стенда.

## Миграции

- Нет.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches`: 201 заказ обрабатывается пачками `100/100/1` без дублей и параллельности; неполный ответ сопоставляется по `order_id`, ошибка средней пачки сохраняет её локальные данные и не останавливает последнюю.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend/tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status`: ручная сверка одного заказа использует batch-клиент с одним ID.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && ruff check app/services/fbs_autopoll_service.py app/services/fbs_marking_service.py tests/test_fbs_marking.py` — успешно: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && mypy app/services/fbs_autopoll_service.py app/services/fbs_marking_service.py` — код выхода 1 из-за четырёх ранее существующих ошибок в импортируемых соседних модулях: `wildberries_credentials_service.py:167`, `fbs_stock_sync_service.py:617`, `fbs_warehouse_binding_service.py:23` и `:291`; в двух модулях атома ошибок не выведено.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/backend && pytest -q tests/test_fbs_marking.py::test_fbs_marking_autopoll_batches_unique_ids_and_skips_partial_or_failed_batches tests/test_fbs_marking.py::test_fbs_marking_sync_updates_check_status` — успешно: `2 passed in 1.84s`.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/back_guard.py` — неприменимо: атом не добавляет маршрут.
- `python3 /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-01-wb-marking/scripts/ci/check_migrations.py` — неприменимо: атом не добавляет миграцию.

## Не реализовано

- Исправление browser evidence из `JUDGE.md`: это вне backend-слоя данного атома; проверка требует живого UI-стенда и снимков зон `S-03`, `S-14`, `S-15`.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод и живой кабинет Wildberries не читались и не затрагивались.

## Блокеры

- Нет для backend-реализации. Browser-проверка из `JUDGE.md` остаётся отдельным непроходимым в этой роли контуром.

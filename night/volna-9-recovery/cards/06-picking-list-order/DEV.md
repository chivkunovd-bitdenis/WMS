# Backend Dev · 06-picking-list-order · атом 3 · переделка

## Что реализовано

- Эндпоинт: существующий `GET /operations/fbs-supplies/{supply_id}/picking-list` перепроверен; он возвращает серверные товарные группы, непрерывные диапазоны `number_start` / `number_end` и канонический полный `order_ids`.
- Сервис: существующий `get_picking_list` перепроверен; группы сортируются по `(article, sku_code, size, product_name)`, а заказы внутри группы — по `wb_order_id`, затем `order.id`.
- Тест: API-сценарий усилен проверкой полного развёрнутого `order_ids` и равенства длины диапазона, `quantity` и количества идентификаторов в каждой строке.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — усилен сценарий `test_fbs_supply_picking_list_grouping`: он проверяет полный канонический порядок всех заказов и согласованность каждого диапазона с количеством строки.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — записан отчёт переделки атома 3.

Существующая реализация в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py` и `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py` уже буквально выполняет контракт; переделка после ревью не потребовала изменения этих файлов.

## Миграции

- Нет: схема данных не менялась.

## Тесты

- `test_fbs_supply_picking_list_grouping` — проверяет перемешанную вставку нескольких товарных групп, пустые и совпадающие товарные признаки, одиночные номера и диапазоны, полный канонический `order_ids`, согласованность количества и повторный идентичный ответ API.

## Гейты

- `ruff check /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — пройдено: `All checks passed!`.
- `mypy /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — не пройдено: `21 errors in 5 files`; ошибки находятся в существующих участках `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`, `test_fbs_shipment_warehouse_sc.py` и старых строках `test_fbs_supply_assembly.py`, новое утверждение их не добавляет.
- `pytest -q /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py -k 'test_fbs_supply_picking_list_grouping'` — пройдено: `1 passed, 18 deselected in 5.29s`.
- `python3 scripts/ci/back_guard.py` — не применим: атом не добавляет и не меняет роут.
- `python3 scripts/ci/check_migrations.py` — не применим: атом не добавляет миграцию.
- `git diff --check -- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — пройдено.
- `git add -- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git diff --cached --check && git commit -m "test(fbs): strengthen picking list sequence coverage"` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock` (`Operation not permitted`).

## Не реализовано

- Находки 1–4 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/REVIEW.md` относятся к подключению модалки, физической печати и frontend-тестам. Они не относятся к backend-файлам и слою атома 3, поэтому в этой переделке не исправлялись.
- Следующие атомы из `FEATURES.md` не выполнялись.

## Блокеры

- Реализация атома, уже существовавшая до переделки, сохранена в истории ветки; текущий `HEAD` — `373ea249`. Усиление теста и новый `DEV.md` локально реализованы, но не сохранены отдельным коммитом: песочница запрещает запись в общую мета-папку Git worktree. Поэтому результат переделки нельзя считать опубликованным или полностью сохранённым в Git.
- Общий типовой gate остаётся красным из-за существующих ошибок вне изменения этого атома; целевой API-сценарий зелёный.

## Находки

- `REVIEW.md` прямо подтверждает корректность серверного листа и ленты; backend-находок для атома 3 нет.
- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались.

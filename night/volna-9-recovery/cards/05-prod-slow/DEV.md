# Backend dev · 05-prod-slow · атом 1 · rework

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wb_marketplace_orders_service.py` — восстановлен полный контракт существующего `sync_seller_orders`: ручная синхронизация снова импортирует новые задания, обходит полный список, обновляет статусы и после полного прохода связывает подтверждённые заказы с WB-поставками; раздельные контуры `sync_new_orders_for_seller` и `reconcile_orders_for_seller` сохранены.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py` — добавлена регрессия совместимости ручной синхронизации со статусной сверкой и привязкой поставок.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md` — записан отчёт атома.

## Что реализовано

- Эндпоинты: новых нет; существующий `POST /operations/fbs-orders/sync` через `sync_seller_orders` снова сохраняет прежний полный результат со `statuses_updated` и сводкой привязки WB-поставок.
- Сервис `sync_seller_orders`: восстановлены импорт `/orders/new`, курсорный полный обход, статусная сверка и привязка поставок; ошибка или цикл курсора не запускают статусную и supply-сверку после незавершённого прохода.
- Сервис `sync_new_orders_for_seller`: остаётся лёгким контуром и не вызывает постраничный полный список.
- Сервис `reconcile_orders_for_seller`: остаётся отдельным полным курсорным обходом и не помечает незавершённую сверку успешной.

## Миграции

Нет.

## Тесты

- `test_legacy_manual_sync_keeps_status_and_supply_reconciliation` — ручной legacy-вход вызывает новый импорт, полный список, обновление статусов и привязку поставок, сохраняя поля прежнего результата.
- `test_new_sync_does_not_fetch_paginated_orders` — лёгкий `new` не обращается к постраничному полному списку.
- `test_reconcile_walks_cursor_and_fails_incomplete_pass`, `test_reconcile_rejects_a_repeated_next_token`, `test_reconcile_walks_past_ten_pages_and_links_supplies` — полный обход до конца, безопасная ошибка/цикл курсора и отсутствие произвольного лимита страниц.
- Регрессии из ревью: `test_fbs_order_status_sync_supplier_confirm_moves_new_to_external_processing`, `test_fbs_order_status_sync_links_external_wb_supply`, `test_fbs_order_status_sync_releases_reserve_on_cancel`.

## Гейты

- `ruff check app/services/wb_marketplace_orders_service.py tests/test_wb_marketplace_orders_service.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend` — PASS, `All checks passed!`.
- `mypy app/services/wb_marketplace_orders_service.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend` — FAIL на четырёх существующих ошибках импортируемых соседних модулей: одна в `wildberries_credentials_service.py`, одна в `fbs_stock_sync_service.py`, две в `fbs_warehouse_binding_service.py`; изменённый `wb_marketplace_orders_service.py` в диагностике отсутствует.
- `pytest -q tests/test_wb_marketplace_orders_service.py tests/test_fbs_orders_intake.py::test_fbs_order_status_sync_supplier_confirm_moves_new_to_external_processing tests/test_fbs_orders_intake.py::test_fbs_order_status_sync_links_external_wb_supply tests/test_fbs_orders_intake.py::test_fbs_order_status_sync_releases_reserve_on_cancel` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend` — PASS, `19 passed in 14.87s`.
- `back_guard.py` не запускался: атом не добавляет роут.
- `check_migrations.py` не запускался: атом не добавляет миграцию.

## Не реализовано

- Остальные находки `REVIEW.md` не относятся к двум разрешённым backend-файлам атома 1 и не исправлялись.
- Полный backend-регресс, `ruff check .` и `mypy .` не запускались: роль требует выполнить их один раз после интеграции всех карточек, а на этом атоме разрешены только адресные проверки.

## Блокеры

- Продуктовых блокеров в границах атома нет.
- Публикация ветки в `origin` не выполнена: `git push -u origin night/volna-9-recovery/lane-2/05-prod-slow` завершился ошибкой `Could not resolve host: github.com` из-за недоступной сети среды. Локальный коммит создан и восстанавливаем из именованной ветки.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

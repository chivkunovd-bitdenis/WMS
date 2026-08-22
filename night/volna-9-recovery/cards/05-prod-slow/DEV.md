# Backend dev · 05-prod-slow · атом 1 · переделка по ревью

## Что реализовано

- Эндпоинты: новых и изменённых эндпоинтов нет.
- Сервис `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wb_marketplace_orders_service.py`: списание `FbsBindingStockPool` теперь читает строку с `FOR UPDATE`, поэтому одновременно разрешённые контуры `new` и `reconcile` не теряют одно из списаний для двух разных заказов одного пула; существующая идемпотентность повторного импорта одного заказа через `UNIQUE(order_id)` сохранена.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wb_marketplace_orders_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/tests/test_wb_marketplace_orders_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/DEV.md`

## Миграции

Нет.

## Тесты

- Добавлен `test_new_and_reconcile_serialize_different_order_debits_on_one_pool`: два параллельных списания разных заказов требуют блокировку строки пула, создают две записи `FbsStockPoolDebit` и уменьшают количество с 10 до 8.
- Повторно проверены атомарные сценарии `new`: отсутствие вызова постраничного полного списка и идемпотентный upsert.
- Повторно проверены атомарные сценарии `reconcile`: полный курсорный обход, отказ считать незавершённый проход успешным после ошибки, обнаружение цикла курсора и отсутствие произвольного лимита в десять страниц.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && ruff check app/services/wb_marketplace_orders_service.py tests/test_wb_marketplace_orders_service.py` — PASS, `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy app/services/wb_marketplace_orders_service.py` — FAIL только на четырёх существующих ошибках импортируемых соседних модулей: `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/wildberries_credentials_service.py:167`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_stock_sync_service.py:617`, `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend/app/services/fbs_warehouse_binding_service.py:23,291`; изменённый модуль в диагностике этой штатной команды отсутствует.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && mypy --follow-imports=skip app/services/wb_marketplace_orders_service.py` — дополнительная узкая попытка завершилась FAIL на 12 ранее существующих `no-any-return` в самом модуле; изменённая функция `_debit_stock_pool_once` в диагностике отсутствует.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q tests/test_wb_marketplace_orders_service.py::test_new_and_reconcile_serialize_different_order_debits_on_one_pool tests/test_wb_marketplace_orders_service.py::test_new_sync_does_not_fetch_paginated_orders tests/test_wb_marketplace_orders_service.py::test_reconcile_walks_cursor_and_fails_incomplete_pass tests/test_wb_marketplace_orders_service.py::test_reconcile_rejects_a_repeated_next_token tests/test_wb_marketplace_orders_service.py::test_reconcile_walks_past_ten_pages_and_links_supplies` — PASS, `5 passed in 0.27s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/backend && pytest -q tests/test_wb_marketplace_orders_service.py` — PASS, `19 passed in 3.88s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow && git diff --check` — PASS.
- `python3 scripts/ci/back_guard.py` не запускался: атом не добавляет и не меняет роуты.
- `python3 scripts/ci/check_migrations.py` не запускался: атом не добавляет миграцию.

## Не реализовано

- Находки ревью №2–6 относятся к фоновым заданиям печати, frontend и документации; они находятся вне двух разрешённых backend-файлов этого атома и не изменялись.
- Полный backend-регресс, `ruff check .` и `mypy .` не запускались: инструкция атома прямо запрещает общий прогон до интеграции всех карточек.
- В `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-05-prod-slow/night/volna-9-recovery/cards/05-prod-slow/CONTRACT.md` нет отдельного раздела «API и данные»; реализация ограничена буквально заданным пользователем атомом и относящейся к нему находкой №1 из `REVIEW.md`.

## Блокеры

- Функциональных блокеров в границах атома нет.
- Локальная реализация не сохранена отдельным Git-коммитом и не опубликована: команда `git add backend/app/services/wb_marketplace_orders_service.py backend/tests/test_wb_marketplace_orders_service.py night/volna-9-recovery/cards/05-prod-slow/DEV.md && git commit -m "fix(wb): serialize concurrent stock pool debits"` остановилась до изменения индекса с `fatal: Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-2-05-prod-slow/index.lock': Operation not permitted`. Риск: изменения пока восстанавливаются только из этой постоянной рабочей копии.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных, боевой прод `194.87.96.144` и живой кабинет Wildberries не читались и не затрагивались.

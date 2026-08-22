# Backend dev · 04-warehouse-switch · атом 3 · rework

## Что реализовано

- `GET /operations/fbs-supplies/worklist` — подтверждена фильтрация по операционному `warehouse_id` текущего tenant без изменения склада исторической поставки.
- `POST /operations/fbs-supplies/from-orders` — подтверждено создание поставки на рекомендованном или явно выбранном операционном складе.
- `PATCH /operations/fbs-supplies/{supply_id}/warehouse` — подтверждена смена склада до начала работы и блокировка после подбора с сообщением «Склад закреплён: подбор уже начат».
- `_raise_from_packaging_integration` — `insufficient_sorting_stock` и `foreign_sorting_location` теперь возвращаются как штатный конфликт `409`, сохраняют конкретное сообщение сервиса и имеют русское резервное объяснение вместо HTTP 500 с техническим кодом.
- Реестр блокировок S-03 — исправлены B-14/B-15 и добавлены отсутствовавшие B-16 `supply_warehouse_locked` и B-17 выбора только операционного склада tenant.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/fbs_supplies.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_fbs_supply_from_orders.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/docs/blockers/S-03.md`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md`

## Миграции

Нет.

## Тесты

- Добавлен параметризованный `test_packaging_warehouse_blocks_return_operator_message`: проверяет для `insufficient_sorting_stock` и `foreign_sorting_location` статус `409`, стабильный error envelope, сохранение конкретного сообщения сервиса и человеко-понятный резервный текст.
- Повторно проверены создание поставки на рекомендованном и вручную выбранном операционном складе, смена склада до первого действия, запрет после подбора, группировка worklist и фильтрация существующих поставок по собственному `warehouse_id`.

## Гейты

- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && ruff check app/api/fbs_supplies.py app/services/fbs_supply_service.py tests/test_fbs_supply_from_orders.py` — пройдено: `All checks passed!`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && mypy app/api/fbs_supplies.py app/services/fbs_supply_service.py tests/test_fbs_supply_from_orders.py` — целевые файлы текущего атома чисты, команда завершилась с кодом 1 из-за двух ошибок в импортируемых соседних модулях вне атома: `app/services/wildberries_credentials_service.py:167` и `app/services/fbs_stock_sync_service.py:617`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && pytest -q tests/test_fbs_supply_from_orders.py -k 'packaging_warehouse_blocks_return_operator_message or warehouse_switch_is_locked_after_pick or creation_uses_selected_operational_warehouse or creation_without_selection_uses_recommended_warehouse or supply_worklist_groups_active_orders_by_supply or supply_worklist_filters_by_operational_warehouse'` — пройдено: `7 passed, 16 deselected in 5.01s`.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git diff --check` — пройдено без замечаний.
- Диагностическая попытка `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend && mypy --follow-imports=skip app/api/fbs_supplies.py app/services/fbs_supply_service.py` не засчитана как гейт: пропуск импортов превратил типы FastAPI/Pydantic в `Any` и дал 144 ложных ошибки; после неё выполнена штатная целевая команда выше.
- `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch && git add -- backend/app/api/fbs_supplies.py backend/tests/test_fbs_supply_from_orders.py docs/blockers/S-03.md night/volna-9-recovery/cards/04-warehouse-switch/DEV.md && git diff --cached --check && git diff --cached --stat && git commit -m 'fix(fbs): map warehouse packaging blocks'` — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock`, ошибка `Operation not permitted`.
- `python3 scripts/ci/back_guard.py` — не запускался: новых маршрутов атом не добавляет.
- `python3 scripts/ci/check_migrations.py` — не запускался: миграций нет.

## Не реализовано

- Frontend-находки REVIEW №1, №2, №3 и №6 не менялись: роль `backend-dev` и границы атома запрещают UI-правки.
- Находка REVIEW №4 относится к соседнему backend-контракту черновика приёмки (`inbound_intake.py`), а не к FBS-поставке атома 3.
- `backend/app/services/fbs_supply_service.py` не потребовал нового diff: создание, смена/закрепление склада и фильтрация worklist уже реализованы буквально и подтверждены назначенными тестами.

## Блокеры

- Реализация и артефакт находятся в постоянном зарегистрированном worktree, но не сохранены отдельным Git-коммитом: sandbox разрешает менять рабочие файлы, однако запрещает запись в общий служебный каталог `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch`. Восстанавливаемого нового commit SHA нет.
- Целевые ruff и pytest зелёные; mypy остановлен только двумя ранее существовавшими ошибками импортируемых соседних модулей вне файлов атома.

## Находки

Нет.

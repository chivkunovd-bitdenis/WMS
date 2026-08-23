# Backend Dev · 06-picking-list-order · атом 1 · переделка по REVIEW

## Что реализовано

- Эндпоинт `GET /operations/fbs-supplies/{supply_id}/picking-list` — вместе с канонически упорядоченными строками возвращает непрозрачный `snapshot`, рассчитанный по атрибутам группировки, `wb_order_id` и внутренним ID заказов.
- Эндпоинт `POST /operations/fbs-supplies/{supply_id}/order-print-tape` — принимает `picking_list_snapshot`, до создания печатных активов сверяет его с текущим каноническим порядком и при расхождении возвращает контрактный `409 stale_picking_list`.
- Сервис `fbs_supply_service` — один общий ключ формирует канонический порядок листа, его строки и версионный SHA-256-снимок; пустой лист тоже получает стабильный снимок.
- Сервис `fbs_order_tape_print_service` — использует тот же общий ключ вместо собственной копии сортировки и отклоняет устаревший снимок до запроса ленты.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_supply_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_packaging_integration.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md`

## Миграции

- Нет: структура базы данных не менялась.

## Тесты

- `test_order_tape_rejects_stale_picking_list_snapshot_before_creating_assets` (`S-03-TC-008`) — открывает лист, меняет канонический `wb_article` без изменения состава `order_ids`, проверяет `409 stale_picking_list` и отсутствие созданных `FbsPrintAsset`; затем получает свежий снимок, печатает полный состав и проверяет новый порядок и номера `1…N`.
- `test_tape_covers_every_order_and_matches_picking_list` — существующая регрессия полной и повторной печати теперь передаёт снимок открытого листа и подтверждает неизменные номера.
- `test_fbs_supply_picking_list_grouping` — дополнительно проверяет стабильность и непрозрачный формат снимка обычного и пустого листа.

## Гейты

- ЗЕЛЁНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` выполнено `git diff --check && cd backend && ruff check app/services/fbs_supply_service.py app/services/fbs_order_tape_print_service.py app/api/fbs_supplies.py tests/test_fbs_supply_assembly.py tests/test_fbs_packaging_integration.py` — `All checks passed!`.
- КРАСНЫЙ только на существующем долге импортируемых соседей: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` выполнено `mypy app/services/fbs_supply_service.py app/services/fbs_order_tape_print_service.py app/api/fbs_supplies.py` — 4 ошибки в неизменённых `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23` и `:291`; в трёх изменённых модулях ошибок нет.
- ЗЕЛЁНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` выполнено `pytest -q tests/test_fbs_supply_assembly.py::test_fbs_supply_picking_list_grouping tests/test_fbs_packaging_integration.py::test_tape_covers_every_order_and_matches_picking_list tests/test_fbs_packaging_integration.py::test_order_tape_rejects_stale_picking_list_snapshot_before_creating_assets` — `3 passed in 3.42s`.
- ЗЕЛЁНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` выполнено `git diff --check -- backend/app/services/fbs_supply_service.py backend/app/services/fbs_order_tape_print_service.py backend/app/api/fbs_supplies.py backend/tests/test_fbs_supply_assembly.py backend/tests/test_fbs_packaging_integration.py night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — ошибок формата diff нет.
- КРАСНЫЙ из-за ограничения файловой системы: `git add -- backend/app/services/fbs_supply_service.py backend/app/services/fbs_order_tape_print_service.py backend/app/api/fbs_supplies.py backend/tests/test_fbs_supply_assembly.py backend/tests/test_fbs_packaging_integration.py night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git diff --cached --check && git commit -m "fix(fbs): validate picking list order snapshot"` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock`: `Operation not permitted`; индекс не изменён, commit не создан.
- `python3 scripts/ci/back_guard.py` не запускался: атом не добавляет новый роут.
- `python3 scripts/ci/check_migrations.py` не запускался: атом не добавляет миграцию.

## Не реализовано

- Следующие атомы `FEATURES.md` не выполнялись. В частности, обязательность снимка будет привязана к явному безопасному режиму печати листа в атоме 2, а frontend начнёт передавать снимок в атоме 3; сейчас совместимая общая ручка проверяет снимок, когда он передан, и сохраняет прежний контракт других режимов.
- Находки 1–3 и 5–9 из `REVIEW.md` относятся к следующим backend/frontend-атомам либо другому слою и не исправлялись.

## Блокеры

- На уровне реализации и целевых тестов блокеров нет. Сохранение результата отдельным Git-коммитом заблокировано запретом записи в общую метапапку worktree; текущий `HEAD` — `de35007609bd1ab0a61c5d009efb8d31c98e5c18`, он не содержит эту переделку. Результат локально реализован, но не сохранён в Git и не опубликован.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
- Несвязанные изменения оркестратора в `JOURNAL.md`, `FEATURES.md` и остальных артефактах карточки сохранены без отката и не относятся к этому атому.

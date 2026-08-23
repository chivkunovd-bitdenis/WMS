# Backend Dev · 06-picking-list-order · атом 2 · переделка по REVIEW

## Что реализовано

- Эндпоинт `POST /operations/fbs-supplies/{supply_id}/order-print-tape` — принимает явный `mode: "picking_list"`; для него требует снимок открытого листа, полный состав поставки и возвращает канонически пронумерованные готовые WB-активы без выпущенных или перепечатанных кодов маркировки.
- Сервис `fbs_order_tape_print_service` — безопасный режим листа не разбирает макет маркировки, не проверяет пул кодов, не выпускает и не перепечатывает коды, не создаёт привязки маркировки, не синхронизирует метаданные с Wildberries и не меняет статус поставки через упаковочную интеграцию.
- Сервис `fbs_order_tape_print_service` — прежний режим `marking` оставлен режимом по умолчанию, поэтому существующие упаковочные запросы без поля `mode` сохраняют прежний контракт печати и синхронизации маркировки.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/api/fbs_supplies.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_order_tape_print.py`
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md`

## Миграции

- Нет: структура базы данных не менялась.

## Тесты

- Добавлен `test_picking_list_mode_does_not_release_reprint_or_sync_marking_codes` (`S-03-TC-004`): полная поставка с обязательным «Честным знаком» печатается через `mode: "picking_list"` и актуальный снимок; ответ содержит готовые WB-активы и постоянные служебные номера, а `codes`/`printed_codes` пусты. Тест также проверяет, что макет маркировки не разбирается, пул не инспектируется, записи выпуска/перепечати и привязки не появляются, доступные коды не меняют статус, а синхронизация с WB не вызывается.
- В том же тесте проверено, что безопасный режим без снимка возвращает `422 picking_list_snapshot_required` до создания печатных активов.
- Регрессия `test_order_print_tape_assigns_codes_to_requested_orders` подтверждает прежний контракт режима по умолчанию: старый запрос без `mode` печатает коды, создаёт привязки и синхронизирует их с WB.
- Регрессии `test_tape_covers_every_order_and_matches_picking_list` и `test_order_tape_rejects_stale_picking_list_snapshot_before_creating_assets` подтверждают полный канонический состав, стабильные номера и отказ по устаревшему снимку.

## Гейты

- ЗЕЛЁНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` выполнено `ruff check app/services/fbs_order_tape_print_service.py app/api/fbs_supplies.py tests/test_fbs_order_tape_print.py` — `All checks passed!`.
- ЦЕЛЕВЫЕ МОДУЛИ ЧИСТЫ, общий результат красный только на существующем долге импортируемых соседей: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` выполнено `mypy app/services/fbs_order_tape_print_service.py app/api/fbs_supplies.py` — 4 ошибки в неизменённых `app/services/wildberries_credentials_service.py:167`, `app/services/fbs_stock_sync_service.py:617`, `app/services/fbs_warehouse_binding_service.py:23` и `:291`; в двух изменённых модулях ошибок нет.
- ЗЕЛЁНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` выполнено `pytest -q tests/test_fbs_order_tape_print.py::test_picking_list_mode_does_not_release_reprint_or_sync_marking_codes tests/test_fbs_box_clear_and_workspace_extras.py::test_order_print_tape_assigns_codes_to_requested_orders tests/test_fbs_packaging_integration.py::test_tape_covers_every_order_and_matches_picking_list tests/test_fbs_packaging_integration.py::test_order_tape_rejects_stale_picking_list_snapshot_before_creating_assets` — `4 passed, 1 warning in 4.25s`; предупреждение — существующий `DeprecationWarning` FastAPI для `HTTP_422_UNPROCESSABLE_ENTITY`.
- ЗЕЛЁНЫЙ: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` выполнено `git diff --check -- backend/app/services/fbs_order_tape_print_service.py backend/app/api/fbs_supplies.py night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — ошибок пробелов и маркеров конфликта нет; новый тест отдельно проверен `ruff` и `pytest`.
- КРАСНЫЙ из-за ограничения файловой системы: из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order` выполнено `git add -- backend/app/services/fbs_order_tape_print_service.py backend/app/api/fbs_supplies.py backend/tests/test_fbs_order_tape_print.py night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git diff --cached --check && git status --short && git diff --cached --stat && git commit -m "fix(fbs): isolate picking-list tape printing"` — Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock`: `Operation not permitted`; индекс не изменён, коммит не создан.
- `python3 scripts/ci/back_guard.py` не запускался: атом не добавляет новый роут, а расширяет тело и ветвление существующего.
- `python3 scripts/ci/check_migrations.py` не запускался: атом не добавляет миграцию.

## Не реализовано

- Следующие атомы `FEATURES.md` не выполнялись: frontend пока не передаёт `mode: "picking_list"`, а упаковочная кнопка, общий API assets, предпросмотр, запрет физической печати неполной ленты, устойчивость загрузки и миграция локальных отметок относятся к атомам 3–8.
- Frontend-файлы из находок 2, 3 и 5–9 `REVIEW.md` не менялись, потому что они находятся вне роли `backend-dev` и границы текущего атома.
- В пунктах текущего атома буквальных отступлений от контракта нет.

## Блокеры

- Реализация и целевые проверки выполнены локально, но сохранить атом отдельным Git-коммитом невозможно из-за запрета записи в общую метапапку worktree. Текущий `HEAD` — `9a96cf292e01fc89222fdc2621148522d27e3f1e`; он не содержит изменения атома 2. До снятия ограничения результат имеет статус «локально реализовано, но не сохранено в Git и не опубликовано».

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
- Несвязанные изменения оркестратора в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/JOURNAL.md` сохранены без отката и в атом не включены.

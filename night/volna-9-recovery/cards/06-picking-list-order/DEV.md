# Backend development report · 06-picking-list-order · атом 4 · переделка по REVIEW

## Что реализовано

- Эндпоинт `POST /operations/fbs-supplies/{supply_id}/order-print-tape` — контракт ответа сохранён; для отсутствующего WB PNG возвращается одна конкретная ошибка с постоянным `order_number`, без второго общего `order_qr_missing`.
- Сервис `print_fbs_order_tape` — ошибка из `PrintBatchResult.order_errors` считается уже зарегистрированной ошибкой WB-стикера; отсутствие готового asset больше не дублирует её, а следующий заказ сохраняет исходный номер полного листа.

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/app/services/fbs_order_tape_print_service.py` — исключено повторное добавление общей ошибки для заказа, по которому batch уже вернул конкретную ошибку WB-стикера.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_supply_assembly.py` — регрессионная проверка усилена до точного требования: у проблемного заказа одна ошибка `wb_sticker_missing` с номером `2`, следующий готовый заказ остаётся номером `3`.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — отчёт текущей переделки.

## Миграции

Нет.

## Тесты

- `test_fbs_order_tape_missing_png_preserves_following_order_number` — перемешанный полный набор нормализуется сервером; отсутствующий PNG даёт ровно одну исходную batch-ошибку с постоянным номером `2`; готовые заказы имеют номера `1` и `3`.
- Существующие `test_fbs_order_tape_*` — полный состав, канонический порядок, стабильная нумерация и совместимость построчной перепечатки.
- `test_tape_covers_every_order_and_matches_picking_list` — интеграционный endpoint-сценарий одинакового порядка листа и ленты при перемешанных ID и повторной печати.

## Гейты

- `ruff check app/services/fbs_order_tape_print_service.py app/api/fbs_supplies.py tests/test_fbs_supply_assembly.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено, `All checks passed!`, код 0.
- `mypy app/services/fbs_order_tape_print_service.py app/api/fbs_supplies.py tests/test_fbs_supply_assembly.py` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — не пройдено: 21 существующая диагностика в 5 файлах, включая транзитивно проверенные `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`, `test_fbs_shipment_warehouse_sc.py` и прежние строки `test_fbs_supply_assembly.py`; изменённые строки новой диагностики не добавили.
- `pytest -q tests/test_fbs_supply_assembly.py -k 'fbs_order_tape'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено: `5 passed, 15 deselected in 0.08s`, код 0.
- `pytest -q tests/test_fbs_packaging_integration.py -k 'tape_covers_every_order_and_matches_picking_list'` из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend` — пройдено: `1 passed, 14 deselected in 1.08s`, код 0.
- `python3 scripts/ci/back_guard.py` — не применим: атом не добавляет и не меняет роут.
- `python3 scripts/ci/check_migrations.py` — не применим: миграций нет.
- `git diff --check -- backend/app/services/fbs_order_tape_print_service.py backend/tests/test_fbs_supply_assembly.py night/volna-9-recovery/cards/06-picking-list-order/DEV.md` из корня рабочей копии — пройдено, код 0.
- `git add -- backend/app/services/fbs_order_tape_print_service.py backend/tests/test_fbs_supply_assembly.py night/volna-9-recovery/cards/06-picking-list-order/DEV.md && git diff --cached --check && git commit -m "fix(fbs): avoid duplicate tape sticker errors"` из корня рабочей копии — не выполнено: Git не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-06-picking-list-order/index.lock`, `Operation not permitted`.

## Не реализовано

- Frontend-часть находки 4 (`FbsPrintPreviewDialog.tsx` показывает одинаковый текст для разных кодов ошибок) не относится к роли `backend-dev` и файлам атома.
- Находки 1–3 и 5–6 из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/REVIEW.md` относятся к frontend-реестру, UI-компонентам, маршруту модалки, режимам предпросмотра и браузерным тестам; они не исправлялись.
- Следующие атомы из `FEATURES.md` не выполнялись.

## Находки

- Секреты, ключи, токены, `.env` и кабинеты учётных данных не читались и не изменялись.
- Несвязанное изменение `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/JOURNAL.md` сохранено без изменений и в коммит атома не включается.

## Блокеры

- Реализация и целевые тесты выполнены локально, но отдельный восстанавливаемый коммит создать невозможно: общая Git-метапапка worktree недоступна среде для записи. Последний сохранённый `HEAD` — `e5230651`; он не содержит текущую переделку.
- Узкий `mypy` имеет существующий технический долг, перечисленный в разделе «Гейты»; новых диагностик на изменённых строках нет.

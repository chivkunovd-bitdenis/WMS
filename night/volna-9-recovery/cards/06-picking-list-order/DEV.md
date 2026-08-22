# Backend development report · 06-picking-list-order

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/backend/tests/test_fbs_packaging_integration.py` — добавлен endpoint-регресс: полный состав в перемешанном порядке возвращается канонически, повторная печать сохраняет порядок и номера.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-06-picking-list-order/night/volna-9-recovery/cards/06-picking-list-order/DEV.md` — этот отчёт.

## Гейты

- `ruff check .` — не пройден: 82 ранее существующие ошибки за пределами изменённого теста; новая проверка не добавила диагностик.
- `mypy .` — не пройден: 21 ранее существующая ошибка в 6 файлах, изменённый тест и backend-атом в списке ошибок отсутствуют.
- `pytest -q tests/test_fbs_packaging_integration.py -k tape_covers_every_order_and_matches_picking_list` — пройден, `1 passed`.
- `pytest -q` — запущен полный набор; к моменту формирования отчёта процесс ещё выполнялся (дошёл минимум до 26% без падений).
- `python3 scripts/ci/back_guard.py` — недоступен в этой рабочей копии: файл отсутствует.
- `python3 scripts/ci/check_migrations.py` — недоступен в этой рабочей копии: файл отсутствует.

## Не реализовано

- Новые backend-роуты, модели и миграции не требовались: endpoint `/operations/fbs-supplies/{supply_id}/order-print-tape` уже канонизирует полный входной набор и возвращает постоянные `order_number`, включая номера в `order_errors` для пропущенных WB-стикеров.
- Живые WB-запросы не выполнялись; тест использует существующую изолированную заглушку.

## Блокеры

- Полные ruff/mypy-гейты заблокированы накопленными ошибками baseline; guard-скрипты отсутствуют в checkout.

# DEV · 04-warehouse-switch · атом 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_warehouses.py` — добавлены регрессии resolver-а для legacy-коллизии штрихкодов и изоляции чужого tenant.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — этот отчёт.

## Что реализовано

- `GET /warehouses/resolve` — существующее разрешение сканов подтверждено тестом: коллизия склада и ячейки возвращает `409 barcode_ambiguous`, а штрихкод другого tenant возвращает `404 barcode_unknown`.
- `catalog_service.resolve_warehouse_scan` — при исторической межсущностной коллизии не выбирает объект по приоритету; это покрыто прямой регрессией на сохранённых данных.

## Миграции

- Нет новых миграций: миграция `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/alembic/versions/20260822_0094_warehouse_operational_barcode.py` уже добавляет `is_operational` и `barcode`, а также помечает `fbs-wb-*` / `FBS WB *` служебными.

## Тесты

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_warehouses.py` — складской штрихкод → `warehouse`, штрихкод ячейки → `location`, legacy-коллизия → понятный `409`, чужой tenant → `404` без раскрытия данных.

## Гейты

- `ruff check .` — не пройден: 80 существующих нарушений вне изменённого файла; `ruff check tests/test_warehouses.py` пройден.
- `mypy .` — не пройден: 21 существующая ошибка в шести других файлах; изменённый тест типовых ошибок не добавил.
- `pytest` — остановлен после 118 passed на двух существующих регрессиях вне атома: `test_document_number_service.py::test_inbound_and_unload_api_assign_document_number` (`product seller not found`) и `test_fbs_manual_pick.py::test_manual_pick_rejects_wrong_cell_product_and_packed_order` (ожидается 404, получен 200). Целевой `pytest tests/test_warehouses.py` — пройден, 1 passed.
- `python3 scripts/ci/back_guard.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/back_guard.py` нет в рабочей копии.
- `python3 scripts/ci/check_migrations.py` — не запущен: файла `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/check_migrations.py` нет в рабочей копии.
- `git diff --check` — пройден.

## Не реализовано

- Находка review №3 о переносе старых FBS-binding/заказов при маркировке legacy-складов относится к следующему атому 3 (`fbs_supply_service.py`) и не затронута: этот проход ограничен атомом 1 и его файлами.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не изменялись.

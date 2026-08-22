# DEV · 04-warehouse-switch · backend-dev

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/models/warehouse.py` — добавлены `is_operational` и уникальный штрихкод склада.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/services/catalog_service.py` — список ограничен операционными складами; резолвер различает склад и ячейку, отклоняет коллизии и ограничивает tenant.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/app/api/warehouses.py` — API возвращает новые поля и тип результата `warehouse`/`location`, ошибки резолвера отдаются понятными кодами HTTP.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/alembic/versions/20260822_0094_warehouse_operational_barcode.py` — добавляет признаки, генерирует штрихкоды, помечает legacy `fbs-wb-*`/`FBS WB *` служебными и оставляет один основной склад операционным.
- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend/tests/test_warehouses.py` — проверяет список, скан склада, скан ячейки и коллизию.

## Миграции

- `20260822_0094` — добавляет `warehouses.is_operational` и `warehouses.barcode`, backfill-ит значения, помечает legacy-склады служебными и создаёт уникальный индекс штрихкода.

## Тесты

- `backend/tests/test_warehouses.py` — 1 тест прошёл: операционный список, типы `warehouse`/`location`, коллизия возвращает `409 barcode_ambiguous`.

## Гейты

- ruff: PASS для изменённых backend-файлов; полный `ruff check .` — FAIL на 84 ранее существующих ошибках, включая unrelated-файлы.
- mypy: FAIL на 25 ранее существующих ошибках в 7 файлах; в затронутых модель/API/catalog-файлах ошибок нет.
- pytest: PASS для `tests/test_warehouses.py` (1 passed); полный прогон не запускался из-за baseline-ошибок quality gates.
- back_guard.py: НЕ ЗАПУЩЕН — файл отсутствует в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/`.
- check_migrations.py: НЕ ЗАПУЩЕН — файл отсутствует в `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/scripts/ci/`.

## Не реализовано

- Остальные атомарные куски карточки 04 не реализованы: изменён только операционный склад и разрешение складского штрихкода.
- UI-переключатель, контекст сессии и интеграция с рабочими экранами не входят в роль backend-dev и не изменялись.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись.

## Блокеры

- Guard-скрипты отсутствуют в этой рабочей копии; это отмечено в гейтах. Код и целевой тест проверены локально.

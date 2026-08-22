# DEV · 04-warehouse-switch · повторная проверка атома 1

## Изменённые файлы

- `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` — записан результат повторной проверки после `REVIEW.md`.

Backend-код атома не менялся: `REVIEW.md` не содержит находок в
`backend/app/models/warehouse.py`,
`backend/alembic/versions/20260822_0094_warehouse_operational_barcode.py`,
`backend/app/api/warehouses.py` или `backend/tests/test_warehouses.py` и отдельно
подтверждает корректность разделения операционных складов, tenant-проверок resolver-а и
отказа при неоднозначном скане.

## Что реализовано

- `GET /warehouses` — ранее реализованный эндпоинт возвращает только операционные склады tenant; служебные `fbs-wb-*` / `FBS WB *` исключаются сервисом списка.
- `GET /warehouses/resolve` — ранее реализованный resolver возвращает `warehouse` для склада и `location` для ячейки, отклоняет неоднозначное значение как `barcode_ambiguous` и не раскрывает объект другого tenant (`barcode_unknown`).
- `catalog_service.resolve_warehouse_scan` — ранее реализованное разрешение проверяет коды и штрихкоды складов и ячеек в одном tenant без выбора по приоритету.

## Миграции

- Новых миграций нет. Существующая `20260822_0094_warehouse_operational_barcode.py` добавляет `warehouses.is_operational` и `warehouses.barcode`, заполняет уникальные складские штрихкоды и помечает legacy `fbs-wb-*` / `FBS WB *` неоперационными.

## Тесты

- Новых тестов в повторном проходе нет: `backend/tests/test_warehouses.py` уже покрывает список операционных складов, типы `warehouse` / `location`, межсущностную legacy-коллизию и изоляцию чужого tenant.

## Гейты

- `ruff check app/models/warehouse.py app/api/warehouses.py app/services/catalog_service.py alembic/versions/20260822_0094_warehouse_operational_barcode.py tests/test_warehouses.py` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend`) — пройдено: `All checks passed!`.
- `mypy app/models/warehouse.py app/api/warehouses.py app/services/catalog_service.py` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend`) — целевые модули проверены, но команда завершилась с кодом 1 из-за четырёх существующих ошибок в импортируемых соседних файлах: `wildberries_credentials_service.py:167`, `fbs_stock_sync_service.py:617`, `fbs_warehouse_binding_service.py:23` и `fbs_warehouse_binding_service.py:294`.
- `pytest -q tests/test_warehouses.py` (из `/Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-1-04-warehouse-switch/backend`) — пройдено: `1 passed in 3.81s`.
- `python3 scripts/ci/back_guard.py` — не применим: повторный проход не добавляет роут; самого файла в рабочей копии также нет.
- `python3 scripts/ci/check_migrations.py` — не применим: повторный проход не добавляет миграцию; самого файла в рабочей копии также нет.

## Не реализовано

- Находки 1–12 из `REVIEW.md` не относятся одновременно к файлам и границам атома 1. Они затрагивают следующие атомы (`preflight`, FBS workspace, общий frontend-контекст, S-01, S-14, S-25, seller draft, движения и blocker registry), поэтому в этом проходе не изменялись.
- В `CONTRACT.md` нет отдельного раздела `API и данные`; точный backend-контракт атома взят из прямо назначенного пользователем пункта 1 `FEATURES.md`. Дополнительное поведение сверх него не добавлялось.

## Блокеры

- Сохранение отчёта отдельным Git-коммитом заблокировано правами среды: команда
  `git add -- night/volna-9-recovery/cards/04-warehouse-switch/DEV.md` завершилась с
  `fatal: Unable to create '/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-1-04-warehouse-switch/index.lock': Operation not permitted`.
  Backend-код не менялся; отчёт записан в рабочую копию, но не сохранён в новом commit SHA.

## Находки

- Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не открывались и не изменялись.

# Backend Dev — 03-no-distribution-mode — фича 3

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/api/fbs_supplies.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/app/services/fbs_workspace_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-03-no-distribution-mode/backend/tests/test_fbs_packing_box.py

Добавлен POST `/operations/fbs-supplies/{supply_id}/boxes-without-distribution`. Он вызывает существующий сервис переключения, возвращает обновлённый workspace и переводит `boxes_already_distributed` в HTTP 409. В workspace добавлено `supply.boxes_without_distribution`; признак читается из сохранённого поля поставки и не исчезает при пустом списке коробов.

## Миграции

Нет: поля поставки и миграция добавлены предыдущей фичей.

## Тесты

Добавлены API-тесты на включение режима без коробов, сохранение флага при повторном GET workspace и конфликт при назначенном заказе.

## Гейты

- ruff: FAIL — существующий `RUF100` для `# ruff: noqa: RUF001` в `/backend/app/services/fbs_workspace_service.py`.
- mypy: FAIL — 4 существующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py` и `fbs_warehouse_binding_service.py`; изменённые файлы новых ошибок не добавили.
- pytest: PASS — целевые тесты `tests/test_fbs_packing_box.py -k boxes_without_distribution_api`: 2 passed.
- back_guard.py: NOT RUN — файл отсутствует в рабочей копии.
- check_migrations.py: NOT RUN — файл отсутствует в рабочей копии.
- git diff --check: PASS.

## Не реализовано

- UI и OpenAPI-файл не изменялись: они относятся к фиче 4 и находятся вне backend-dev атомарного куска.
- Массовая миграция legacy-ключей `no-distribution:` не выполнялась: контракт оставляет совместимость на чтение существующего формата.

## Находки

- Секреты, ключи, токены и `.env` не читались.
- В рабочем дереве до этой работы уже были изменения `night/volna-9-recovery/JOURNAL.md`; они не относятся к реализации и не включались в отчёт как изменённый backend-файл.

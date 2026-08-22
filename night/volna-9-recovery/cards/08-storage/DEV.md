# DEV · 08-storage · атом 7

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/services/storage_statement_service.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/backend/app/api/storage.py
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-2-08-storage/night/volna-9-recovery/cards/08-storage/DEV.md

## Что реализовано

- Фиксация повторно использует уже опубликованный ledger для измерений и не создаёт дубли.
- Выбор тарифа детерминирован: индивидуальный тариф имеет приоритет над общим, затем берётся последняя версия, действующая на начало периода.
- Нулевой statement публикует одну нулевую ledger-строку.
- Печать ограничена измерениями конкретного tenant/seller/warehouse/month и возвращает ставку-снимок, сумму строки и единый service/source contract.

## Гейты

- ruff: PASS для изменённых `storage_statement_service.py` и `storage.py`.
- mypy: FAIL: внешний `app.models.billing` отсутствует в этой рабочей копии; также полный запуск выявляет существующие ошибки в `wildberries_credentials_service.py`, `fbs_stock_sync_service.py`, `fbs_warehouse_binding_service.py`.
- pytest: PASS, `5 passed` для `tests/test_storage_statement_service.py tests/test_storage_models.py`.
- back_guard.py: не запускался до полного backend-гейта; ожидает отсутствующий общий billing-контракт.
- check_migrations.py: не запускался, миграции атома не менялись.

## Не реализовано

- Внешние модели `BillingTariffVersion` и `BillingLedgerEntry` не добавлялись: это обязательная зависимость 09-A, а создание локальных storage-тарифов или второго ledger запрещено `ARCH-CROSS.md`.
- Тесты конкурентных API-запросов и финансового DTO не расширены: текущая ветка не содержит billing-моделей/схемы, на которой их можно выполнить.

## Находки

- В рабочем дереве отсутствует общий billing-контракт 09-A; это техническая зависимость, не секрет и не причина останавливать остальные проверки.

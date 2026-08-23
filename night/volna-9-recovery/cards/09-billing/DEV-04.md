# 09-billing · backend-dev · атом 4

## Изменённые файлы

- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/inbound_intake_service.py — `post_all_remaining` завершает проверенную нулевую приёмку, создаёт единственное начисление и не создаёт зону сортировки без фактического товара.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/app/services/billing_ledger_service.py — сумма начисления приводится к целому числу копеек, чтобы новый нулевой сценарий и документный тариф сохранялись в `INTEGER`-поле финансового журнала.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend/tests/test_inbound_intake_service_sort_be01.py — добавлены сценарии нулевой приёмки с тарифом за документ, повтором без второго начисления и с поштучным тарифом с нулевой суммой.
- /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/night/volna-9-recovery/cards/09-billing/DEV.md — отчёт этого атома.

## Миграции

Нет.

## Тесты

- `test_zero_actual_intake_closes_and_charges_document_tariff_once` проводит документ с явно установленным фактом `0` через проверку и массовое завершение, проверяет статус `done`, одно начисление за документ на 4 500 копеек и отсутствие второго начисления при повторе.
- `test_zero_actual_intake_closes_with_zero_item_tariff_amount` проверяет, что при поштучном тарифе та же складская операция завершается, а начисление содержит количество и сумму `0`.

## Гейты

- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && ruff check app/services/inbound_intake_service.py app/services/billing_ledger_service.py tests/test_inbound_intake_service_sort_be01.py tests/test_billing_ledger_service.py` — `All checks passed!`.
- Красный вне этого атома: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && mypy app/services/inbound_intake_service.py app/services/billing_ledger_service.py` — 4 унаследованные ошибки в импортируемых `app/services/wildberries_credentials_service.py`, `app/services/fbs_stock_sync_service.py` и `app/services/fbs_warehouse_binding_service.py`; в двух проверяемых модулях ошибок не сообщено.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing/backend && pytest -q tests/test_inbound_intake_service_sort_be01.py tests/test_billing_ledger_service.py` — `14 passed`.
- Зелёный: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git diff --check` — ошибок пробелов нет.
- `python3 scripts/ci/back_guard.py` не применим: маршруты в атоме не добавлялись. `python3 scripts/ci/check_migrations.py` не применим: миграций нет.
- Не сохранено новым Git-коммитом: `cd /Users/deniscivkunov/Projects/WMS/.worktrees/.night-worktrees/volna-9-recovery/lane-3-09-billing && git add backend/app/services/inbound_intake_service.py backend/app/services/billing_ledger_service.py backend/tests/test_inbound_intake_service_sort_be01.py night/volna-9-recovery/cards/09-billing/DEV.md` не смог создать `/Users/deniscivkunov/Projects/WMS/.git/worktrees/lane-3-09-billing1/index.lock` (`Operation not permitted`).

## Не реализовано

Нет: реализован только атом 4 из `FEATURES.md`; соседние продуктовые задачи не затрагивались.

## Находки

Секреты, ключи, токены, `.env`, кабинеты учётных данных и боевой прод не читались и не изменялись. Целевая проверка выявила и устранила связанный с ранее переведёнными на копейки моделями дефект: сервис журнала передавал `Decimal` в `INTEGER`-сумму.

# Волна 2А — доказательства реализации

Дата: 2026-08-26. Worktree: `billing-module-20260826`.

Исходная принятая продуктовая база —
`772a2982ea2a2a11be17664f5f44aa302f427be7`; перед product commit HEAD содержит
только принятый amendment наряда `f8e9fb66324d5d30549f8cf02553bf25cac5f68d`.
Frontend, маршруты и OpenAPI не менялись: browser/Playwright/ui_guard и OpenAPI
diff не применимы к backend/data волне 2А.

## Поведенческие проверки

| Команда | Exit code | Результат |
|---|---:|---|
| `cd backend && uv run pytest tests/test_operation_facts.py tests/test_storage_statement_service.py::test_concurrent_fix_publishes_one_immutable_ledger_and_repeatable_print -q` | 0 | 6 passed |
| `cd backend && uv run pytest tests/test_fbs_picking.py -q` | 0 | 9 passed |
| `cd backend && uv run pytest tests/test_fbs_supply_from_orders.py -q` | 0 | 16 passed, 1 skipped |
| `cd backend && uv run pytest tests/test_operation_facts.py tests/test_operation_fact_recovery.py tests/test_packaging_tasks.py tests/test_fbs_packaging_integration.py tests/test_marketplace_unload_completion.py tests/test_seller_marketplace_unload.py tests/test_ozon_marketplace_unload.py tests/test_storage_statement_service.py -q` | 0 | 69 passed |
| `cd backend && uv run pytest` | 0 | 1152 passed, 6 skipped, 9 inherited deprecation warnings, 1884.56 s |

`test_wb_fbs_pick_undo_and_redo_write_three_real_source_facts` выполняет реальные
HTTP-переходы WB `pick → undo → repeat undo with same key → redo` и находит ровно
`fbs_pick`, `fbs_pick_reversal`, `fbs_pick`. SQLite fidelity для уже существующего
PostgreSQL partial unique index подтверждена добавлением только
`sqlite_where=text('undone_at IS NULL')` к индексу модели; production schema и
поведение от этого не изменяются.

## Машинные гейты

| Команда | Exit code | Результат |
|---|---:|---|
| `cd backend && uv run ruff check .` | 0 | All checks passed |
| `cd backend && uv run mypy .` | 0 | Success: no issues found in 339 source files |
| `python3 scripts/ci/check_migrations.py` | 0 | 22 migrations checked; destructive operations not found |
| `cd backend && uv run alembic heads` | 0 | exactly one head: `20260826_0110` |
| `git diff --check` | 0 | empty output |
| `python3 scripts/ci/back_guard.py` before the separate baseline commit | 1 | only the four approved source-service line baselines below are new |

## PostgreSQL upgrade and constraint proof

Local compose service `billing-module-20260826-db-1` (host port 5433) was created
solely for this proof; production and staging were not touched.

| Команда | Exit code | Результат |
|---|---:|---|
| `DATABASE_URL=...localhost:5433/wms uv run alembic upgrade 20260825_0109` | 0 | migration chain reached previous head |
| `DATABASE_URL=...localhost:5433/wms uv run alembic upgrade 20260826_0110` | 0 | additive operation-facts migration applied immediately |
| `DATABASE_URL=...localhost:5433/wms uv run alembic heads` | 0 | exactly `20260826_0110 (head)` |
| `docker compose exec -T db psql ... pg_indexes/pg_constraint/alembic_version` | 0 | source unique, partial idempotency, report indexes, FK/check constraints and version verified |
| `DATABASE_URL=...localhost:5433/wms uv run pytest tests/test_operation_fact_recovery.py::test_wb_fbs_pick_undo_and_redo_write_three_real_source_facts tests/test_storage_statement_service.py::test_concurrent_fix_publishes_one_immutable_ledger_and_repeatable_print -q` | 0 | 2 passed on PostgreSQL |

The PostgreSQL inspection returned `uq_operation_facts_source_operation`, partial
`uq_operation_facts_tenant_idempotency WHERE idempotency_key IS NOT NULL`, all three
tenant/seller/actor/operation report indexes, fact/line foreign keys, quantity and
source checks, cutover singleton check, and `alembic_version=20260826_0110`.

## Scope and remaining baseline step

The product diff contains the additive migration, fact/line metadata, writer and
recovery services, source integrations, and 2А tests only. There is no API/UI
addition, no `DocumentEvent` dependency, and the existing
`staff_packaging_billing_service` regression passed in the full suite.

The only open mechanical step is the explicit separate baseline commit documented
in `BACK_GUARD_BASELINE.md`; its JSON is deliberately still unchanged at this point.

# Волна 2А — correction round 1: доказательства

Дата: 2026-08-26. Worktree: `billing-module-20260826`.

Исходный product SHA: `b35302b145b5f353b5577c11b4584cfc11f6125a`.
Исходный baseline SHA: `b532addd7862d807e8b3933faf272a50bb2421d5`.
Correction product SHA: `0f0fc49135c4b577304431d96d1e1e48f1ad5798`;
additive migration guard fix: `aa5d0925582ceaec31fa2c36caf3fdde7d0bf5c1`.
Отдельный baseline SHA: `a07b0c5c06ca4e9170971f7eb95c7e4f9d6072a0`.

Frontend, routes, OpenAPI, legacy ledger и `DocumentEvent` не менялись.

## Тесты и машинные гейты

| Команда | Exit code | Результат |
|---|---:|---|
| `cd backend && uv run pytest tests/test_operation_facts.py tests/test_operation_fact_recovery.py -q` | 0 | 12 passed |
| `cd backend && uv run pytest` | 0 | 1156 passed, 6 skipped, 9 warnings, 1092.00 s |
| `cd backend && uv run ruff check .` | 0 | All checks passed |
| `cd backend && uv run mypy .` | 0 | Success: no issues found in 340 source files |
| `python3 scripts/ci/check_migrations.py` | 0 | 24 migrations checked; destructive operations not found |
| `cd backend && uv run alembic heads` | 0 | exactly `20260826_0111 (head)` |
| `python3 scripts/ci/back_guard.py` | 0 | no new deviations |
| `git diff --check` | 0 | empty output |

## PostgreSQL migration and behavior proof

Only the local compose PostgreSQL service was used; staging and production were not touched.
On a fresh local database, `alembic upgrade 20260825_0109` followed by
`alembic upgrade head` exited 0 and produced the single `20260826_0111` head.
Inspection confirmed tenant-scoped fact seller/actor/reversal FKs, tenant-scoped
line fact/product FKs and `ck_operation_fact_lines_tenant_required`.

The behavior script exited 0 and proved:

- strict `source_event_ids` recovery created one shipped unload fact, then one
  system-cancel reversal, and a third identical recovery created zero facts;
- PostgreSQL rejected both a cross-tenant seller relation and a cross-tenant fact line;
- writer snapshot kept the original tenant-scoped actor email after that user was renamed and deleted.

The correction adds only durable unload timestamps, tenant-scoped fact relations,
actor snapshots and recovery filtering. It does not add money, UI, API or 2B work.

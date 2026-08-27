# Seller report Wave 3 — проверочный протокол

Проверен кандидат ветки `codex/billing-module-20260826`. Базовая миграционная
разница Wave 3 пуста: `git diff --exit-code 18d5a557 -- backend/alembic` завершилась
с кодом 0. В репозитории остаётся ранее принятая миграция `0113`; санкция ниже
относится только к ней, а не к новой миграции Wave 3.

## Backend

* `cd backend && uv run pytest tests/test_billing_seller_report_service.py tests/test_billing_seller_report_api.py tests/test_billing_invoice_service.py -q` — `22 passed in 9.41s`.
  Эти API-тесты используют тестовую БД и покрывают серверную агрегацию, foreign-tenant
  cursor, tamper/filter binding, storage-строку, finance off/on, mixed/unpriced rate
  и цепочку charge/reversal/cancelled invoice history.
* Root-managed `cd backend && uv run pytest` — `1175 passed, 10 skipped, 9 warnings in 1094.44s (0:18:14)`, exit 0.
* `cd backend && uv run ruff check .` и `cd backend && uv run mypy .` — exit 0:
  `All checks passed!`; `Success: no issues found in 345 source files` (совместный запуск 3.38s).

## Frontend

* `npm run test:unit && npx tsc --noEmit -p tsconfig.app.json && npm run build && npm run test:e2e` — exit 0:
  unit `212 passed (35 files)`; TypeScript exit 0; production build exit 0;
  Playwright `214 passed, 7 skipped (17.1m)`.
* `npx playwright test frontend/tests-e2e/billing-seller-report.spec.ts frontend/tests-e2e/billing-ledger.spec.ts frontend/tests-e2e/billing-invoices.spec.ts` — `14 passed (56.7s)`.

## Guards

* `python3 scripts/ci/back_guard.py` — exit 0, `новых отступлений нет`.
* `WMS_DESTRUCTIVE_MIGRATION_APPROVED=yes python3 scripts/ci/check_migrations.py` — exit 0. Он обнаружил только четыре `op.execute` в неизменённой принятой
  `20260827_0113_billing_tariff_matrix_integrity.py`; санкция применена только к этому
  заранее известному случаю.
* `python3 scripts/ui/ui_guard.py` — exit 0, `новых отступлений нет`.
* `git diff --check` — exit 0.

Скриншоты и `VERDICT.md` намеренно не созданы: живую браузерную приёмку и её
доказательства оформляет независимый судья после candidate commit.

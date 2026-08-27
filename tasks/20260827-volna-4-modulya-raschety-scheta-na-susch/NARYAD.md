# Наряд · 20260827-volna-4-modulya-raschety-scheta-na-susch

**Полоса:** обычная
**Тип:** экран
**Заведён:** 27.08.2026 15:04

## Просили дословно

> Волна 4 модуля «Расчёты»: счета на существующем /app/ff/billing

## Экраны

- экраны не назначены (новый экран или не UI-задача)

## Изоляция worktree

Перед открытием наряда проверено: `git rev-parse --show-toplevel` вернул
`/Users/deniscivkunov/Projects/WMS/.worktrees/billing-module-20260826`, а
`git rev-parse --git-common-dir` — `/Users/deniscivkunov/Projects/WMS/.git`.
Это постоянный worktree внутри единственной копии проекта, а не отдельный clone.

## Границы правки

Разрешено трогать только эти файлы:

- `backend/alembic/versions/20260827_0114_billing_invoice_v2.py`
- `backend/app/api/billing.py`
- `backend/app/api/billing_invoice_v2_schemas.py`
- `backend/app/celery_app.py`
- `backend/app/models/__init__.py`
- `backend/app/models/billing.py`
- `backend/app/models/operation_fact.py`
- `backend/app/services/billing_invoice_service.py`
- `backend/app/services/billing_invoice_v2_service.py`
- `backend/app/services/billing_seller_report_service.py`
- `backend/app/tasks/billing_tasks.py`
- `backend/tests/test_billing_invoice_api.py`
- `backend/tests/test_billing_invoice_service.py`
- `backend/tests/test_billing_invoice_v2_api.py`
- `backend/tests/test_billing_invoice_v2_service.py`
- `backend/tests/test_billing_seller_report_service.py`
- `backend/tests/test_billing_tasks.py`
- `docs/evidence/20260827-volna-4-modulya-raschety-scheta-na-susch/BILLING-INVOICE-PREVIEW-1280.jpg`
- `docs/evidence/20260827-volna-4-modulya-raschety-scheta-na-susch/BILLING-INVOICE-PREVIEW-1600.jpg`
- `docs/evidence/20260827-volna-4-modulya-raschety-scheta-na-susch/BILLING-INVOICE-PRINT-1600.jpg`
- `docs/evidence/20260827-volna-4-modulya-raschety-scheta-na-susch/VERDICT.md`
- `docs/evidence/billing-04-invoices/INVOICE-V2-PROOF.md`
- `frontend/src/screens/ff/FfBillingScreen.test.ts`
- `frontend/src/screens/ff/FfBillingScreen.tsx`
- `frontend/tests-e2e/billing-invoice-v2.spec.ts`
- `frontend/tests-e2e/billing-invoices.spec.ts`
- `frontend/tests-e2e/billing-seller-report.spec.ts`

## Статус

- [ ] арх-решение — не требуется (правка существующего)
- [ ] контракт (обычная полоса)
- [ ] разработка
- [ ] критик исполнения
- [ ] судья в живом браузере
- [ ] доказательства в `docs/evidence/20260827-volna-4-modulya-raschety-scheta-na-susch/`
- [ ] влито

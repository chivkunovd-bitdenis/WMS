# Наряд · 20260826-volna-2b-modulya-raschety-tarifnaya-matr

**Полоса:** обычная
**Тип:** экран
**Заведён:** 26.08.2026 23:40

## Просили дословно

> Волна 2Б модуля «Расчёты»: тарифная матрица на экране Настройки ФФ

## Экраны

- `S-19` /app/ff/settings — FfSettingsScreen

## Границы правки

Разрешено трогать только эти файлы:

- `backend/alembic/versions/20260826_0112_billing_tariff_matrix.py`
- `backend/app/api/billing.py`
- `backend/app/main.py`
- `backend/app/models/__init__.py`
- `backend/app/models/billing.py`
- `backend/app/models/packaging_task.py`
- `backend/app/services/auth_service.py`
- `backend/app/services/billing_configuration_service.py`
- `backend/app/services/billing_ledger_service.py`
- `backend/app/services/billing_tariff_matrix_service.py`
- `backend/app/services/inbound_intake_service.py`
- `backend/app/services/marketplace_unload_service.py`
- `backend/tests/test_auth.py`
- `backend/tests/test_billing_configuration_api.py`
- `backend/tests/test_billing_invoice_api.py`
- `backend/tests/test_billing_invoice_service.py`
- `backend/tests/test_billing_ledger_service.py`
- `backend/tests/test_billing_tariff_matrix.py`
- `backend/tests/test_bootstrap_billing_tariff_matrix.py`
- `backend/tests/test_inbound_intake_service_sort_be01.py`
- `backend/tests/test_marketplace_unload_and_discrepancy_acts.py`
- `backend/tests/test_staff_packaging_billing.py`
- `docs/backend-guard-baseline.json`
- `docs/evidence/billing-02b-tariff-matrix/OPERATION-FACTS-PROOF.md`
- `frontend/src/api.ts`
- `frontend/src/screens/ff/FfBillingTariffMatrixPanel.tsx`
- `frontend/src/screens/ff/FfSettingsScreen.test.tsx`
- `frontend/src/screens/ff/FfSettingsScreen.tsx`
- `frontend/src/utils/ffPermissions.ts`
- `frontend/src/utils/separateMarkingPrint.ts`
- `frontend/tests-e2e/billing-invoices.spec.ts`
- `frontend/tests-e2e/billing-ledger.spec.ts`
- `frontend/tests-e2e/ff-billing-tariff-matrix.spec.ts`
- `frontend/tests-e2e/ff-staff-users.spec.ts`

## Общие файлы (в границы не входят)

Правка любого из них задевает соседние экраны. Нужен — включай явно:
`--shared <путь>` при создании наряда, и назови это в отчёте.

* `frontend/src/api.ts` — экраны: S-03, S-04, S-05, S-07, S-08, S-09, S-10, S-12, S-13, S-14, S-15, S-16, S-18, S-19, S-26, S-27, S-28, S-29, S-30, S-31, S-32 (не включён)
* `frontend/src/utils/readApiErrorMessage.ts` — экраны: S-03, S-04, S-05, S-07, S-08, S-09, S-10, S-12, S-14, S-16, S-18, S-19, S-26, S-27, S-28, S-29, S-31, S-32 (не включён)

## Статус

- [ ] арх-решение — не требуется (правка существующего)
- [ ] контракт (обычная полоса)
- [ ] разработка
- [ ] критик исполнения
- [ ] судья в живом браузере
- [ ] доказательства в `docs/evidence/20260826-volna-2b-modulya-raschety-tarifnaya-matr/`
- [ ] влито

# Наряд · 20260821-pechat-vsego-v-fbs-sklikat-shk-i-chz-do-

**Полоса:** аварийная
**Тип:** экран
**Заведён:** 21.08.2026 12:24

## Просили дословно

> печать всего в ФБС: скликать ШК и ЧЗ до нуля, лента только с QR и строго все заказы поставки; галочка «сдать без ЧЗ»; на упаковке не блокировать; предпросмотр должен отражать реальную картину

## Экраны

- `S-03` /app/ff/fbs — FfFbsOrdersScreen

## Границы правки

Разрешено трогать только эти файлы:

- `backend/alembic/versions`
- `backend/app/api/fbs_supplies.py`
- `backend/app/api/packaging_tasks.py`
- `backend/app/models/fbs_supply.py`
- `backend/app/services/fbs_marking_service.py`
- `backend/app/services/fbs_order_tape_print_service.py`
- `backend/app/services/fbs_packaging_integration_service.py`
- `backend/app/services/fbs_shipment_service.py`
- `backend/app/services/fbs_supply_service.py`
- `backend/app/services/fbs_workspace_service.py`
- `backend/app/services/packaging_task_service.py`
- `backend/tests`
- `frontend/src/components/MarkingLabelPreview.tsx`
- `frontend/src/components/MarkingPrintDialog.tsx`
- `frontend/src/components/fbs/FbsChips.tsx`
- `frontend/src/screens/v2/FbsPrintPreviewDialog.tsx`
- `frontend/src/screens/v2/FbsSupplyCreateDialog.tsx`
- `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `frontend/src/screens/v2/fbsApi.ts`
- `frontend/src/screens/v2/fbsUx.ts`
- `frontend/src/utils/useMarkingCodePrint.tsx`

## Общие файлы (в границы не входят)

Правка любого из них задевает соседние экраны. Нужен — включай явно:
`--shared <путь>` при создании наряда, и назови это в отчёте.

* `frontend/src/api.ts` — экраны: S-03, S-04, S-05, S-07, S-08, S-09, S-10, S-12, S-13, S-14, S-15, S-16, S-18, S-19, S-26, S-27, S-28, S-29, S-30, S-31, S-32 (не включён)
* `frontend/src/components/ProductPhotoThumb.tsx` — экраны: S-03, S-05, S-12, S-14, S-16, S-26, S-27, S-28, S-29, S-31 (не включён)
* `frontend/src/screens/ff/FfPackagingPage.tsx` — экраны: S-03, S-12, S-14 (не включён)
* `frontend/src/screens/v2/FfFbsSectionNav.tsx` — экраны: S-03, S-04 (не включён)
* `frontend/src/screens/v2/fbsApi.ts` — экраны: S-03, S-04 (не включён)
* `frontend/src/utils/printProductThermalLabel.ts` — экраны: S-03, S-09, S-14 (не включён)
* `frontend/src/utils/readApiErrorMessage.ts` — экраны: S-03, S-04, S-05, S-07, S-08, S-09, S-10, S-12, S-14, S-16, S-18, S-19, S-26, S-27, S-28, S-29, S-31, S-32 (не включён)
* `frontend/src/utils/useMarkingCodePrint.tsx` — экраны: S-03, S-05, S-12, S-14, S-15, S-27 (не включён)

## Статус

- [ ] арх-решение — не требуется (правка существующего)
- [ ] контракт (обычная полоса)
- [ ] разработка
- [ ] критик исполнения
- [ ] судья в живом браузере
- [ ] доказательства в `docs/evidence/20260821-pechat-vsego-v-fbs-sklikat-shk-i-chz-do-/`
- [ ] влито

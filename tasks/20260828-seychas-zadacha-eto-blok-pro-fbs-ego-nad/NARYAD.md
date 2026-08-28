# Наряд · 20260828-seychas-zadacha-eto-blok-pro-fbs-ego-nad

**Полоса:** обычная
**Тип:** экран
**Заведён:** 28.08.2026 11:58

## Просили дословно

> сейчас задача это блок про фбс - его надо отдельно будет выкатить на прод

## Экраны

- `S-16` /app/ff/products — FfProductsCatalogScreen
- `S-04` /app/ff/fbs/stock-sync — FfFbsStockSyncScreen
- `S-03` /app/ff/fbs — FfFbsOrdersScreen

## Границы правки

Разрешено трогать только эти файлы:

- `backend/app/api/fbs_orders.py`
- `backend/app/api/fbs_sellers.py`
- `backend/app/api/products.py`
- `backend/app/models/fbs_binding_stock_pool.py`
- `backend/app/models/fbs_warehouse_binding.py`
- `backend/app/models/product.py`
- `backend/app/services/catalog_service.py`
- `backend/app/services/fbs_assembly_time_service.py`
- `backend/app/services/fbs_autopoll_service.py`
- `backend/app/services/fbs_stock_rule_service.py`
- `backend/app/services/fbs_stock_availability_service.py`
- `backend/app/services/fbs_stock_sync_service.py`
- `backend/app/services/fbs_warehouse_binding_service.py`
- `backend/app/services/fbs_worklist_service.py`
- `backend/app/services/seller_wb_catalog_service.py`
- `frontend/src/components/FfProductMarkingPrintProvider.tsx`
- `frontend/src/components/fbs/FbsChips.tsx`
- `frontend/src/screens/ff/FfManualProductCreateDialog.tsx`
- `frontend/src/screens/ff/FfProductTzImportDialog.tsx`
- `frontend/src/screens/ff/FfSellerCreateDialog.tsx`
- `frontend/src/screens/v2/FbsPrintPreviewDialog.tsx`
- `frontend/src/screens/v2/FbsSupplyCreateDialog.tsx`
- `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `frontend/src/screens/v2/FfFbsStockSyncScreen.tsx`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `frontend/src/screens/v2/FfProductsCatalogScreen.tsx`
- `frontend/src/screens/v2/fbsUx.ts`

## Общие файлы (в границы не входят)

Правка любого из них задевает соседние экраны. Нужен — включай явно:
`--shared <путь>` при создании наряда, и назови это в отчёте.

* `frontend/src/api.ts` — экраны: S-03, S-04, S-05, S-07, S-08, S-09, S-10, S-12, S-13, S-14, S-15, S-16, S-18, S-19, S-26, S-27, S-28, S-29, S-30, S-31, S-32 (не включён)
* `frontend/src/components/ProductBarcodeCell.tsx` — экраны: S-12, S-14, S-16, S-26, S-28, S-29 (не включён)
* `frontend/src/components/ProductBarcodePrintButton.tsx` — экраны: S-05, S-12, S-14, S-16, S-27 (не включён)
* `frontend/src/components/ProductPhotoThumb.tsx` — экраны: S-03, S-05, S-12, S-14, S-16, S-26, S-27, S-28, S-29, S-31 (не включён)
* `frontend/src/screens/ff/FfPackagingPage.tsx` — экраны: S-03, S-12, S-14 (не включён)
* `frontend/src/screens/v2/FfFbsSectionNav.tsx` — экраны: S-03, S-04 (не включён)
* `frontend/src/screens/v2/fbsApi.ts` — экраны: S-03, S-04 (не включён)
* `frontend/src/types/wbProductCatalog.ts` — экраны: S-05, S-12, S-14, S-16, S-27 (не включён)
* `frontend/src/utils/latestRequestSequence.ts` — экраны: S-12, S-16, S-26 (не включён)
* `frontend/src/utils/printPackagingInstructions.ts` — экраны: S-16, S-31 (не включён)
* `frontend/src/utils/printProductThermalLabel.ts` — экраны: S-03, S-09, S-14 (не включён)
* `frontend/src/utils/productLabelText.ts` — экраны: S-09, S-12, S-16, S-28, S-29 (не включён)
* `frontend/src/utils/readApiErrorMessage.ts` — экраны: S-03, S-04, S-05, S-07, S-08, S-09, S-10, S-12, S-14, S-16, S-18, S-19, S-26, S-27, S-28, S-29, S-31, S-32 (не включён)
* `frontend/src/utils/useFfProductMarkingPrint.tsx` — экраны: S-05, S-16, S-27 (не включён)
* `frontend/src/utils/useMarkingCodePrint.tsx` — экраны: S-03, S-05, S-12, S-14, S-15, S-27 (не включён)

## Статус

- [ ] арх-решение — не требуется (правка существующего)
- [ ] контракт (обычная полоса)
- [ ] разработка
- [ ] критик исполнения
- [ ] судья в живом браузере
- [ ] доказательства в `docs/evidence/20260828-seychas-zadacha-eto-blok-pro-fbs-ego-nad/`
- [ ] влито

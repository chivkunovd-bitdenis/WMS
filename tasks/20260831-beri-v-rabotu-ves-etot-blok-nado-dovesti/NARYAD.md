# Наряд · 20260831-beri-v-rabotu-ves-etot-blok-nado-dovesti

**Полоса:** обычная
**Тип:** экран
**Заведён:** 31.08.2026 11:41

## Просили дословно

> бери в работу весь этот блок, надо довести до ума. фронт только не поломай пожалуйста - не трогай ничего лишнего

## Экраны

- `S-16` /app/ff/products — FfProductsCatalogScreen

## Границы правки

Разрешено трогать только эти файлы:

- `backend/app/api/fbs_sellers.py`
- `backend/app/services/fbs_warehouse_binding_service.py`
- `frontend/src/components/FfProductMarkingPrintProvider.tsx`
- `frontend/src/screens/ff/FfManualProductCreateDialog.tsx`
- `frontend/src/screens/ff/FfProductTzImportDialog.tsx`
- `frontend/src/screens/ff/FfSellerCreateDialog.tsx`
- `frontend/src/screens/ff/products-fbs/FbsStockDialog.tsx`
- `frontend/src/screens/ff/products-fbs/stub.ts`
- `frontend/src/screens/v2/FfProductsCatalogScreen.tsx`

## Общие файлы (в границы не входят)

Правка любого из них задевает соседние экраны. Нужен — включай явно:
`--shared <путь>` при создании наряда, и назови это в отчёте.

* `frontend/src/api.ts` — экраны: S-03, S-04, S-05, S-07, S-08, S-09, S-10, S-12, S-13, S-14, S-15, S-16, S-18, S-19, S-26, S-27, S-28, S-29, S-30, S-31, S-32 (не включён)
* `frontend/src/components/ProductBarcodeCell.tsx` — экраны: S-12, S-14, S-16, S-26, S-28, S-29 (не включён)
* `frontend/src/components/ProductBarcodePrintButton.tsx` — экраны: S-05, S-12, S-14, S-16, S-27 (не включён)
* `frontend/src/components/ProductPhotoThumb.tsx` — экраны: S-03, S-05, S-12, S-14, S-16, S-26, S-27, S-28, S-29, S-31 (не включён)
* `frontend/src/types/wbProductCatalog.ts` — экраны: S-05, S-12, S-14, S-16, S-27 (не включён)
* `frontend/src/utils/latestRequestSequence.ts` — экраны: S-12, S-16, S-26 (не включён)
* `frontend/src/utils/printPackagingInstructions.ts` — экраны: S-16, S-31 (не включён)
* `frontend/src/utils/productLabelText.ts` — экраны: S-09, S-12, S-16, S-28, S-29 (не включён)
* `frontend/src/utils/readApiErrorMessage.ts` — экраны: S-03, S-04, S-05, S-07, S-08, S-09, S-10, S-12, S-14, S-16, S-18, S-19, S-26, S-27, S-28, S-29, S-31, S-32 (не включён)
* `frontend/src/utils/useFfProductMarkingPrint.tsx` — экраны: S-05, S-16, S-27 (не включён)

## Статус

- [x] арх-решение — не требуется (правка существующего)
- [x] контракт — действующий `tasks/20260828-ekran-tovary-i-fbs-bolshaya-modalka-osta/CONTRACT.md`, раздел 2
- [x] разработка — ветка `fix/fbs-seller-warehouses-20260831`, коммит `c2ea3871`
- [ ] критик исполнения
- [x] судья в живом браузере — прошёл сам, локальный стенд 5182
- [x] доказательства в `docs/evidence/20260831-beri-v-rabotu-ves-etot-blok-nado-dovesti/`
- [ ] влито

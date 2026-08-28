# Наряд · 20260828-podklyuchit-ekran-raspredeleniya-ostatko

**Полоса:** обычная
**Тип:** экран
**Заведён:** 28.08.2026 19:15

## Просили дословно

> подключить экран распределения остатков ФБС с ползунками и настройки складов продавца к боевому API

## Экраны

- `S-16` /app/ff/products — FfProductsCatalogScreen

## Границы правки

Разрешено трогать только эти файлы:

- `frontend/src/components/FfProductMarkingPrintProvider.tsx`
- `frontend/src/screens/ff/FfManualProductCreateDialog.tsx`
- `frontend/src/screens/ff/FfProductTzImportDialog.tsx`
- `frontend/src/screens/ff/FfSellerCreateDialog.tsx`
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

- [ ] арх-решение — не требуется (правка существующего)
- [ ] контракт (обычная полоса)
- [ ] разработка
- [ ] критик исполнения
- [ ] судья в живом браузере
- [ ] доказательства в `docs/evidence/20260828-podklyuchit-ekran-raspredeleniya-ostatko/`
- [ ] влито

# Наряд · 20260821-dobryy-den-pytpyus-sozdat-zayavku-na-pri

**Полоса:** обычная
**Тип:** экран
**Заведён:** 21.08.2026 13:36

## Просили дословно

> Добрый день. Пытпюсь создать заявку на прием товаров. У меня не активна кнопка Добавить. Нажимаю и ничего не происходит

## Экраны

- `S-29` /inbound/new — SellerInboundDraftScreen

## Границы правки

Разрешено трогать только эти файлы:

- `frontend/src/components/WbProductPickerDialog.tsx`
- `frontend/tests-e2e/seller-cabinet.spec.ts`

## Общие файлы (в границы не входят)

Правка любого из них задевает соседние экраны. Нужен — включай явно:
`--shared <путь>` при создании наряда, и назови это в отчёте.

* `frontend/src/api.ts` — экраны: S-03, S-04, S-05, S-07, S-08, S-09, S-10, S-12, S-13, S-14, S-15, S-16, S-18, S-19, S-26, S-27, S-28, S-29, S-30, S-31, S-32 (не включён)
* `frontend/src/components/ProductBarcodeCell.tsx` — экраны: S-12, S-14, S-16, S-26, S-28, S-29 (не включён)
* `frontend/src/components/ProductPhotoThumb.tsx` — экраны: S-03, S-05, S-12, S-14, S-16, S-26, S-27, S-28, S-29, S-31 (не включён)
* `frontend/src/components/SellerWbProductPickerDialog.tsx` — экраны: S-26, S-28, S-29 (не включён)
* `frontend/src/components/WbProductPickerDialog.tsx` — экраны: S-12, S-28, S-29 (включён)
* `frontend/src/components/WmsDateField.tsx` — экраны: S-12, S-26, S-28, S-29 (не включён)
* `frontend/src/screens/v2/SellerInboundDraftScreen.tsx` — экраны: S-28, S-29 (не включён)
* `frontend/src/utils/productLabelText.ts` — экраны: S-09, S-12, S-16, S-28, S-29 (не включён)
* `frontend/src/utils/readApiErrorMessage.ts` — экраны: S-03, S-04, S-05, S-07, S-08, S-09, S-10, S-12, S-14, S-16, S-18, S-19, S-26, S-27, S-28, S-29, S-31, S-32 (не включён)

## Статус

- [ ] арх-решение — не требуется (правка существующего)
- [x] контракт (обычная полоса) — `CONTRACT.md`
- [x] разработка
- [x] критик исполнения — изменение ограничено состоянием ui-kit-кнопки; новых вёрсток, цветов или компонентов нет
- [ ] судья в живом браузере
- [ ] доказательства в `docs/evidence/20260821-dobryy-den-pytpyus-sozdat-zayavku-na-pri/`
- [ ] влито

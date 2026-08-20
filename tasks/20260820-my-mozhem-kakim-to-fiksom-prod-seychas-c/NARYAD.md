# Наряд · 20260820-my-mozhem-kakim-to-fiksom-prod-seychas-c

**Полоса:** аварийная
**Тип:** экран
**Заведён:** 20.08.2026 09:33

## Просили дословно

> мы можем каким то фиксом прод сейчас чисто полечить? чтобы они заказы соьбрали ?

## Экраны

- `S-03` /app/ff/fbs — FfFbsOrdersScreen

## Границы правки

Разрешено трогать только эти файлы:

- `frontend/src/components/fbs/FbsChips.tsx`
- `frontend/src/screens/v2/FbsPrintPreviewDialog.tsx`
- `frontend/src/screens/v2/FbsSupplyCreateDialog.tsx`
- `frontend/src/screens/v2/FfFbsOrdersScreen.tsx`
- `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
- `frontend/src/screens/v2/fbsUx.ts`
- `frontend/tests-e2e/ff-fbs-orders.spec.ts`

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

- [x] арх-решение — не требуется (правка существующего)
- [ ] контракт (обычная полоса)
- [x] разработка
- [ ] критик исполнения
- [ ] судья в живом браузере
- [x] доказательства в `docs/evidence/20260820-my-mozhem-kakim-to-fiksom-prod-seychas-c/`
- [ ] влито

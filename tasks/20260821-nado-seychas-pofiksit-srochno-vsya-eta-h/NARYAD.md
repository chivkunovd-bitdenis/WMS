# Наряд · 20260821-nado-seychas-pofiksit-srochno-vsya-eta-h

**Полоса:** аварийная
**Тип:** экран
**Заведён:** 21.08.2026 10:18

## Просили дословно

> надо сейчас пофиксить срочно — вся эта хуйня, что требует ячейки, что не пропускает, типа ждём ВБ, вот эту историю с печатью; цель минимум — чтобы они могли собрать ФБС и пройти весь путь нормально; хотя бы костыльно быстро на прод

## Экраны

- `S-03` /app/ff/fbs — FfFbsOrdersScreen

## Границы правки

Разрешено трогать только эти файлы:

- `backend/app/api/fbs_supplies.py`
- `backend/app/services/fbs_marking_service.py`
- `backend/app/services/fbs_supply_service.py`
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
- [ ] доказательства в `docs/evidence/20260821-nado-seychas-pofiksit-srochno-vsya-eta-h/`
- [ ] влито

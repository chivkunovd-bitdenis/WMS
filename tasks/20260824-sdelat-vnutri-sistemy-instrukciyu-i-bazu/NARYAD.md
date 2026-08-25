# Наряд · 20260824-sdelat-vnutri-sistemy-instrukciyu-i-bazu

**Полоса:** обычная
**Тип:** экран
**Заведён:** 24.08.2026 23:31

## Просили дословно

> Сделать внутри системы инструкцию и базу знаний по процессу создания приёмки: путь от селлера к ФФ и до фактической приёмки, с красивыми скриншотами и обведёнными кнопками. Только этот процесс.

## Экраны

- `S-17` /app/ff/reception — FfInboundQueuePage
- `S-28` /inbound/:requestId — SellerInboundDraftScreen
- `S-29` /inbound/new — SellerInboundDraftScreen

## Границы правки

Разрешено трогать только эти файлы:

- `docs/evidence/20260824-sdelat-vnutri-sistemy-instrukciyu-i-bazu/README.md`
- `docs/evidence/20260824-sdelat-vnutri-sistemy-instrukciyu-i-bazu/01-ff-knowledge-top.jpg`
- `docs/evidence/20260824-sdelat-vnutri-sistemy-instrukciyu-i-bazu/02-knowledge-seller-steps.jpg`
- `docs/evidence/20260824-sdelat-vnutri-sistemy-instrukciyu-i-bazu/03-knowledge-ff-queue-step.jpg`
- `docs/evidence/20260824-sdelat-vnutri-sistemy-instrukciyu-i-bazu/03-knowledge-ff-steps.jpg`
- `docs/evidence/20260824-sdelat-vnutri-sistemy-instrukciyu-i-bazu/04-knowledge-full-page.jpg`
- `frontend/public/knowledge/inbound/01-seller-documents.jpg`
- `frontend/public/knowledge/inbound/02-seller-inbound-form.jpg`
- `frontend/public/knowledge/inbound/03-ff-reception-queue.jpg`
- `frontend/public/knowledge/inbound/04-ff-receiving-card.jpg`
- `frontend/src/App.tsx`
- `frontend/src/apps/seller/SellerApp.tsx`
- `frontend/src/apps/seller/SellerLayout.tsx`
- `frontend/src/layouts/AuthedAppLayout.tsx`
- `frontend/src/screens/shared/KnowledgeBaseScreen.tsx`
- `frontend/tests-e2e/knowledge-base.spec.ts`

## Общие файлы (в границы не входят)

Правка любого из них задевает соседние экраны. Нужен — включай явно:
`--shared <путь>` при создании наряда, и назови это в отчёте.

* `frontend/src/api.ts` — экраны: S-03, S-04, S-05, S-07, S-08, S-09, S-10, S-12, S-13, S-14, S-15, S-16, S-18, S-19, S-26, S-27, S-28, S-29, S-30, S-31, S-32 (не включён)
* `frontend/src/components/ProductBarcodeCell.tsx` — экраны: S-12, S-14, S-16, S-26, S-28, S-29 (не включён)
* `frontend/src/components/ProductPhotoThumb.tsx` — экраны: S-03, S-05, S-12, S-14, S-16, S-26, S-27, S-28, S-29, S-31 (не включён)
* `frontend/src/components/SellerWbProductPickerDialog.tsx` — экраны: S-26, S-28, S-29 (не включён)
* `frontend/src/components/WbProductPickerDialog.tsx` — экраны: S-12, S-28, S-29 (не включён)
* `frontend/src/components/WmsDateField.tsx` — экраны: S-12, S-26, S-28, S-29 (не включён)
* `frontend/src/screens/ff/FfInboundQueuePage.tsx` — экраны: S-17, S-20 (не включён)
* `frontend/src/screens/v2/SellerInboundDraftScreen.tsx` — экраны: S-28, S-29 (не включён)
* `frontend/src/ui/PageHeader.tsx` — экраны: S-01, S-05, S-07, S-08, S-09, S-12, S-14, S-15, S-17, S-20, S-21, S-22, S-23, S-24, S-25, S-27 (не включён)
* `frontend/src/utils/formatDateTimeLocal.ts` — экраны: S-12, S-17, S-20 (не включён)
* `frontend/src/utils/inboundQueues.ts` — экраны: S-12, S-17, S-20 (не включён)
* `frontend/src/utils/productLabelText.ts` — экраны: S-09, S-12, S-16, S-28, S-29 (не включён)
* `frontend/src/utils/readApiErrorMessage.ts` — экраны: S-03, S-04, S-05, S-07, S-08, S-09, S-10, S-12, S-14, S-16, S-18, S-19, S-26, S-27, S-28, S-29, S-31, S-32 (не включён)

## Статус

- [x] арх-решение — не требуется (правка существующего)
- [x] контракт (обычная полоса) — `CONTRACT.md`
- [x] разработка
- [x] критик исполнения
- [x] судья в живом браузере
- [x] доказательства в `docs/evidence/20260824-sdelat-vnutri-sistemy-instrukciyu-i-bazu/`
- [ ] влито

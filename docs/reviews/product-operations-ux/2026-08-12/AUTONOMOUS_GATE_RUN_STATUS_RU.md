# Автономный статус WMS-gate итерации

Дата старта: 2026-08-12.

Git-root:

```text
/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812
```

Ветка:

```text
iteration/wms-product-ux-features-20260812
```

Базовый SHA перед текущей волной:

```text
cf5aa16ea5214671f515be3cbc358c33bd9522a7
```

## Нельзя

- Нельзя деплоить на staging, пока каждая включённая в релиз фича не прошла Product/UX, Code Review и живой Browser Product QA.
- Нельзя считать unit/API/build заменой browser QA.
- Нельзя добавлять в commit временные QA-БД: `backend/qa-*.db`.
- Нельзя добавлять чужие untracked B06/live-review артефакты без отдельного решения.
- Нельзя трогать секреты, Railway variables, кабинеты ключей и secret panels.

## Product/UX gate пройден и per-feature browser QA пройден

- F01: приёмка без отдельной упаковочной воронки.
- F04: ручной товар из приёмки как вторичный аварийный путь.
- F06: накладная из приёмки печатается по факту.
- F07: MP/FBO shipped read-only + FBS-like hybrid flow.
- F11: упрощённый FF catalog без внутренних стадий и UI-noise.
- F12: monthly stock snapshot с минимальным FF inventory UI.
- F13: scoped-доступ к товарам селлера.
- F15: удаление только там, где backend реально разрешает.
- F16: nmID назван по-русски как `Артикул WB`.
- F17: единый MP/FBO print sheet с колонкой `Факт`, без FBS QR и технического мусора.

## Product/UX gate пройден, но browser QA ещё нужен

- F02: габариты из строки приёмки; code review passed, нужен live browser QA.
- F03: расхождения и добавление товаров селлера; code review passed после backend fix, нужен повторный live browser QA.
- F18: возврат как вариант inbound-процесса; Product/UX approved after BA/UX rework, нужен dev -> code review -> browser QA.

## Product rejected, dev не стартовать без нового Product OK

- F08: направления остатков/FBS-пул; текущий UI смешивает старый FBS toggle и новый drawer, нет полного CRUD.
- F14: сотрудники/права; меню, direct routes и backend API пока не синхронизированы.
- F19: автопечать возврата была rejected; BA/UX rework ready, но повторный Product/UX verdict ещё pending.

## In rework после failed code review

- F05: inbound-часть карточки исправлена, но code review нашёл raw MP statuses `collecting/cancelled` в seller documents. Нужно добить и снова запустить code review.

## Pending strict gates

- F01-F06: inbound/receiving фичи.
- F09-F10: зависят от F08.
- F16: русское название nmID.
- F18-F19: возвраты через приёмку и автопечать ШК.

## Следующий порядок

1. Дождаться Browser QA по F12 и F13.
2. Запустить browser QA по F02/F03.
3. Добить F05 raw MP statuses и повторить code review/browser QA.
4. По F18 запускать dev только в рамках approved BA/UX rework.
5. По F19 сначала повторить Product/UX rereview; dev запрещён до `PRODUCT_APPROVED_FOR_DEV`.
6. По F08/F14 не стартовать dev до нового Product/UX OK.
7. После всех включённых per-feature browser QA запустить общий Final Integration Reviewer.
8. После общего review провести общий живой browser regression по затронутым процессам.
9. Только потом commit, push, Railway staging deploy и проверка, что staging собран из итогового SHA.

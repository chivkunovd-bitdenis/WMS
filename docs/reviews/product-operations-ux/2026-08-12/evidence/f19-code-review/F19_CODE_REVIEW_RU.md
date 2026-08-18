# F19 Code Review: возврат со сканированием и автопечатью ШК

Дата: 2026-08-13
Роль: isolated Code Review Agent
Git-root: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`
Review target: dev commit `0d87bc3c6bbefc1546f3d4b7467e9553e54bb26f` (`F19 restrict return scan autoprint`)

## Verdict

`CODE_REVIEW_PASSED`

F19 соответствует Product / UX verdict из
`docs/reviews/product-operations-ux/2026-08-12/evidence/f19-product-rereview/F19_PRODUCT_REREVIEW_RU.md`.
Критичных дефектов или регрессий в границах code review не найдено.

Этот verdict закрывает только Gate 5. Он не заменяет живой Browser Product QA.

## Проверенный контракт

- Возвратный scan остаётся основным действием: successful `/receiving/scan` возвращает строку, после чего экран обновляет факт и фокусирует scan input.
- Автопечать запускается только из `scanToReceiving`, только при `isReturnOperation && returnAutoPrint`.
- Источник печати ограничен `line.wb_barcode?.trim()`. `sku_code` не используется как fallback.
- При отсутствии `wb_barcode` печать fail-closed: показывается `У товара нет ШК WB для печати.`, печатный вызов не выполняется.
- `applyPicker` в receiving mode больше не вызывает автопечать.
- `onManualProductCreated` в receiving mode больше не вызывает автопечать.
- Auto-print flow вызывает `printBarcodeLabel` напрямую и не открывает `MarkingPrintDialog`.
- Switch `Печатать ШК при скане` рендерится только внутри `isReturnOperation ? (...) : null`, рядом со scan input / scan button.

## Evidence by file

### `frontend/src/screens/ff/FfInboundRequestView.tsx`

- `printReturnBarcodeForLine` на строках commit-view `910-929`: берёт только `wb_barcode`, показывает человеческую ошибку при пустом WB ШК, не подставляет SKU.
- `applyPicker` на строках commit-view `1064-1120`: ручное добавление факта вызывает `/receiving/lines`, но не вызывает `printReturnBarcodeForLine`.
- `onManualProductCreated` на строках commit-view `1122-1148`: ручное создание товара добавляет факт, но не вызывает `printReturnBarcodeForLine`; ошибка добавления не закрывает процесс молча.
- `scanToReceiving` на строках commit-view `1216-1246`: печать находится только после successful scan response и только под `isReturnOperation && returnAutoPrint`.
- UI scan panel на строках commit-view `1966-2034`: один компактный switch, без новых колонок, чипов, статусов или технического текста; обычная приёмка switch не видит.

### `frontend/tests-e2e/inbound-receiving-v2.spec.ts`

- Тест `inbound receiving v2 — return accepts seller catalog discrepancy and dimensions` расширен проверками F19.
- `PRINT_SENTINEL` и browser-side capture фиксируют отсутствие печати на manual picker и manual product creation.
- Scan товара с разными `sku_code` и `wb_barcode` проверяет, что captured print содержит WB barcode и не содержит SKU.
- Проверяется, что `marking-print-dialog` не появляется в auto-print scan flow.

## Findings

No blocking findings.

Неблокирующий риск: рабочее дерево во время ревью было грязным поверх `HEAD`, включая незакоммиченные изменения в тех же двух F19-файлах. Поэтому code inspection привязан к dev commit `0d87bc3c6bbefc1546f3d4b7467e9553e54bb26f`, а локальные тесты ниже прогонялись на текущем dirty worktree. Чужие изменения не staging'ились.

Неблокирующий тестовый зазор: dev commit покрывает manual picker/manual create/no SKU fallback/no MarkingPrintDialog в e2e, а missing `wb_barcode` проверен code inspection. Для Browser Product QA missing-WB path всё равно должен быть пройден руками, как требует Product verdict.

## Tests run

- `backend/`: `pytest tests/test_inbound_intake.py -q` -> `15 passed in 17.00s`.
- `frontend/`: `npm run build` -> passed (`tsc -b && vite build`), Vite chunk-size warning only.
- `frontend/`: `npm run test:e2e -- inbound-receiving-v2.spec.ts -g "return accepts seller catalog discrepancy and dimensions"` -> `1 passed`.

## Gate state

- local: code review выполнен локально.
- committed: pending at artifact creation time.
- pushed: not requested, not performed.
- deployed: not requested, not performed.
- browser-tested: not by this Code Review Agent; targeted Playwright e2e was run, but it is not a substitute for Browser Product QA gate.
- remaining risks: Browser Product QA must still validate the real UI paths for ordinary inbound hidden switch, return visible switch, manual actions no-print, scan +1, WB-only print payload, missing WB fail-closed, and compact desktop/mobile geometry.

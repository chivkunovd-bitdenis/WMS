# Final Browser Regression Rerun: Packaging / Marking / MP Print / Delete Only Draft

Дата: 2026-08-14, Europe/Moscow.

Verdict: `FINAL_BROWSER_GROUP_PASSED`

browser_used: `yes`

## Контур

- Repo: `/Users/deniscivkunov/Projects/WMS/.worktrees/product-operations-ux-20260812`.
- Browser: Chromium через Playwright, `headless=false`, `--kiosk-printing`.
- Viewport: `1280x720`.
- Frontend: `http://127.0.0.1:55214`.
- API: `http://127.0.0.1:18214`, `/health` вернул `{"status":"ok"}`.
- SQLite: `/tmp/wms-final-packaging-delete-live-strict-18214-rerun-1786666801.sqlite`.
- Code/staging/production/Railway/secrets/commit/push: не трогались.
- Evidence JSON: `live-run-result-final.json`.
- Raw harness JSON сохранён отдельно: `live-run-result.json`.
- Print HTML capture: `mp-print-html-capture.json`.

## Live Routes

- `/` - регистрация FF admin.
- `/app/ff/packaging` - очередь, создание задания, сканер, manual, undo, history/reload.
- `/app/ff/packaging` - отдельное задание для pending marking.
- `/seller/` и `/seller/documents` - seller документы и удаление черновика.
- `/app/ff/mp-shipments?open_mp=31589782-14d4-415d-bae6-36e4b3567c8e` - MP/FBO отгрузка, короба, упаковка, финальная печать.

## Live Clicks

Ключевые клики через реальный UI:

- FF registration: `go-to-register`, `Создать аккаунт`.
- Packaging: `Создать задание`, выбор склада, выбор ячейки, выбор строк seller A/B, submit.
- Scanner/manual: valid scan, invalid scan, manual `+2`, undo open, undo confirm, final scans, overscan, complete.
- Pending marking: create no-KM packaging task, open `Осталось промаркировать`.
- Seller MP: login, documents, create MP unload, select WB warehouse, add product, plan.
- FF MP: open submitted, confirm, boxes tab, create box, fill box from location, packaging tab, complete, final tab, click `Печать листа отгрузки`.
- Seller delete: open documents, click draft delete, cancel confirm, reopen, confirm delete.

## Проверки

### R01 / F07: Packaging And Marking

PASS.

- Задание создано из реальной ячейки `PACK-12059`.
- В create-dialog видны seller identity для разных строк: `Final Seller A 1786667012059` и `Final Seller B 1786667012059`.
- Mixed-seller task заблокирован: create disabled, human text `Нельзя создать одно задание для разных селлеров...`.
- Decimal qty `1.5` даёт human helper `Введите целое число`.
- Valid scan обновил строку до `Готово 1 / Осталось 3 / Всего 4`.
- Invalid barcode показал `ШК не найден в этом задании. Проверьте товар и выбранное задание.`, без `unknown_barcode`.
- Manual `+2` сработал, undo-dialog объяснил `2 шт`, read-back вернулся к `Готово 1 / Осталось 3 / Всего 4`.
- Overscan показал `По этому товару всё уже упаковано.`, без `line_already_packed`.
- Complete дал `Выполнено`.
- Reload сохранил `Выполнено`, `Готово 4 / Осталось 0 / Всего 4` и history.
- History содержит `+1 скан`, `+2 вручную`, `Отмена 2 шт`, `Задание выполнено`.
- Pending marking показывает `Нет КМ`, seller name, `Запросите КМ у селлера`, без `__SORTING__` и raw codes.

### F17: MP/FBO Final Print

PASS.

- На финальной вкладке visible/enabled button: `Печать листа отгрузки`.
- Клик по кнопке выполнен в браузере; native dialog не блокировал прогон.
- Generated print HTML captured in `mp-print-html-capture.json`.
- HTML содержит seller, date `2026-06-15`, type `Отгрузка на МП`, quantity `4`, product/barcode data, and `Факт` column.
- HTML не содержит FBS order QR, FBS labels, raw UUID.

### F15: Delete Only Draft

PASS.

- Seller `/seller/documents`: draft inbound has delete action.
- Submitted/non-draft inbound has no delete action.
- Cancel confirmation first: draft row stayed visible.
- Confirm delete: success `Черновик удалён`, draft disappeared, submitted row remained.
- API read-back after delete: draft id absent, submitted id present.
- FF MP submitted/non-draft has no line delete controls.
- FF non-draft box-line remove control is hidden in UI.
- Direct non-draft box-line remove returned `409 {"detail":"not_draft"}` and read-back preserved the box line.
- No raw `not_draft` / `not_editable` was visible in the tested UI surfaces.

## Metrics

All measured 1280px surfaces had no page-level horizontal overflow:

- Packaging route/create/task/scan/manual/undo/history/reload: `documentScrollWidth=1280`, `documentClientWidth=1280`.
- Pending marking: `documentScrollWidth=1280`, `documentClientWidth=1280`.
- Seller MP planning and FF MP submitted/boxes/packaging/final print: `documentScrollWidth=1280`, `documentClientWidth=1280`.
- Seller documents delete flow: `documentScrollWidth=1280`, `documentClientWidth=1280`.

Visible raw-code scan across measured pages found no `unknown_barcode`, `line_already_packed`, `invalid_qty`, `not_draft`, `not_editable`, or `__SORTING__`.

Product judgement at 1280: no black strip observed in the reviewed screenshots, no clipped key controls in the tested flow, and the tested UI did not read as overloaded or ambiguous for the operator tasks.

## Screenshots

Primary screenshots:

- `01-ff-admin-registered-1280x720.png`
- `04-packaging-create-location-two-sellers-1280x720.png`
- `05-packaging-create-mixed-seller-block-1280x720.png`
- `07-packaging-valid-scan-success-1280x720.png`
- `08-packaging-invalid-barcode-human-error-1280x720.png`
- `09-packaging-manual-undo-confirm-1280x720.png`
- `10-packaging-undo-readback-1280x720.png`
- `11-packaging-overpack-human-error-1280x720.png`
- `12-packaging-completed-history-1280x720.png`
- `13-packaging-completed-reload-readback-1280x720.png`
- `14-pending-marking-no-km-human-labels-1280x720.png`
- `16-ff-mp-submitted-no-delete-1280x720.png`
- `17-ff-mp-confirmed-box-filled-no-remove-visible-1280x720.png`
- `18-ff-mp-packaging-complete-1280x720.png`
- `19-ff-mp-final-print-button-1280x720.png`
- `21-seller-documents-before-delete-continuation-1280x720.png`
- `22-seller-delete-confirm-dialog-continuation-1280x720.png`
- `23-seller-delete-after-confirm-continuation-1280x720.png`

Additional harness screenshots are left in the same evidence folder for audit:

- `02-fatal-fixture-1280x720.png` - first seed attempt used an invalid no-location posting fixture and was discarded.
- `20-fatal-product-qa-1280x720.png` - first run stopped while trying to logout under an open MP modal; seller delete was completed in continuation.
- `22-seller-delete-continuation-fatal-1280x720.png` - first continuation had a screenshot-helper error before mutation; second continuation succeeded.

## Harness Notes

The official verdict uses `live-run-result-final.json`.

`live-run-result.json` is preserved because it is useful audit evidence. It contained two harness issues:

- A false-negative history assertion looked for capital `Скан`; the live UI correctly showed lowercase `+1 скан`, plus manual/undo/complete history.
- Seller delete did not run in that raw pass because the harness attempted `logout` while an MP modal was still intercepting pointer events.

The second continuation completed seller delete through the real browser and produced the final PASS evidence.

## Blockers

None.

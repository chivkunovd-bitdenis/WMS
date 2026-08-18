# Live Chrome Product Acceptance: wave1-reception-doc

- Screen: Приёмка на FF — документ
- Stage: live product acceptance round 2 after REC-03 fix
- Started: 2026-08-15T09:25:14.931Z
- Browser: Chrome/151.0.7922.138; CDP http://127.0.0.1:9227; visible external Google Chrome window
- Base URL: http://127.0.0.1:5184
- Commit under test: worktree after 3650f66 plus local REC-03 fix

## Verdict

SCREEN_APPROVED candidate: no findings in round 2.

## Findings

- Стоп 0 / Тормоз 0 / Хвост 0

## Checks

- PASS: REC-03-api-seller-draft-blocked — seller-created draft returns not_submitted before handoff
- PASS: REC-03-ui-seller-draft-no-start — Seller-created draft has no FF start before handoff
- PASS: REC-03-ui-seller-handoff-starts — seller-created starts only after seller handoff and FF start
- PASS: REC-03-ui-ff-direct-receiving — FF-created document starts without seller handoff
- PASS: REC-04-no-visible-scanner-block — No visible scanner block
- PASS: REC-05-add-product-main-action — Top action is “Добавить товар”
- PASS: REC-04-scan-plus-one — Known scan increments 0 -> 1 -> 2
- PASS: REC-05-added-product-row — Added catalog product appears as discrepancy line
- PASS: REC-15-dimensions-weight-volume-visible — Line and totals show dimensions, liters and weight
- PASS: REC-09-packages-collapsed-default — Packages accordion collapsed by default
- PASS: REC-09-boxes-cargo-places — Boxes and cargo places are separate under accordion
- PASS: REC-13-14-row-colors-no-summary-no-distribution — Green/red rows visible, no extra summary chips/blocks and no document distribution panel
- PASS: REC-07-approve-reject-statuses — Discrepancy act statuses change to approved/rejected
- PASS: REC-07-approve-stock-movement — Inventory summary changed after approving discrepancy act
- PASS: 6a-hidden-Дата приёмки (план) — Дата приёмки (план) not visible
- PASS: 6a-hidden-Печать накладной — Печать накладной not visible
- PASS: 6a-hidden-Загрузить по накладной — Загрузить по накладной not visible
- PASS: 6a-hidden-Распределить по ячейкам — Распределить по ячейкам not visible
- PASS: 6a-hidden-Итог приемки — Итог приемки not visible
- PASS: 6a-hidden-Что не так — Что не так not visible
- PASS: 6a-hidden-Сканер штрихкода — Сканер штрихкода not visible

## Screenshots

- 01-ff-queue-seller-draft-and-ff-draft.png: FF queue before seller handoff and FF direct start
- 02-seller-draft-before-handoff-no-start.png: Seller-created draft before handoff has no FF start action
- 03-seller-draft-submit-to-warehouse.png: Seller-created draft handoff in seller portal
- 04-seller-created-after-handoff-ff-start.png: Seller-created document after handoff can be started by FF
- 05-ff-created-draft-direct-start.png: FF-created draft direct start
- 06-ff-created-receiving-scanner-first.png: FF-created document receiving
- 07-scan-known-barcode-plus-one-green-row.png: Known scan increments +1 and row turns green
- 08-unknown-barcode-offers-add-product.png: Unknown scan offers add product
- 09-added-product-red-row-dimensions-totals.png: Added product row, dimensions and totals
- 10-product-barcode-print-dialog.png: Row product barcode print dialog
- 11-packages-expanded-actions-no-import.png: Boxes/cargo actions, no invoice import
- 12-box-and-cargo-place-rows-with-print-actions.png: Box and cargo place rows with print actions
- 13-complete-receiving-discrepancy-dialog.png: Completion discrepancy dialog
- 14-after-complete-sorting-no-distribution-in-doc.png: After completion sorting alert, no distribution table in document
- 15-discrepancy-acts-confirmed-approve-reject-visible.png: Confirmed discrepancy acts with approve/reject
- 16-discrepancy-acts-approved-rejected-statuses.png: Approved and rejected act statuses

## API Evidence

`sellerDraftBeginBeforeSubmit`: {"status":409,"body":{"detail":"not_submitted"}}

`balanceBeforeActApprove`: [{"product_id":"a5b8f909-941f-4ecc-aeee-2a6d95cc51b1","sku_code":"EXTRA-1786785914933","product_name":"Live Extra Product","seller_id":null,"seller_name":null,"packaging_instructions":null,"requires_honest_sign":false,"quantity":1,"quantity_unpacked":1,"quantity_packed":0,"quantity_in_sorting":1,"quantity_in_storage":0,"reserved":0,"available":0,"quantity_fbs":0,"quantity_reserved_directions":0,"quantity_free_fbo":1},{"product_id":"5703d070-f362-4395-ab00-0a3015396c43","sku_code":"PLAN-1786785914933","product_name":"Live Plan Product","seller_id":null,"seller_name":null,"packaging_instructions":null,"requires_honest_sign":false,"quantity":2,"quantity_unpacked":2,"quantity_packed":0,"quantity_in_sorting":2,"quantity_in_storage":0,"reserved":0,"available":0,"quantity_fbs":0,"quantity_reserved_directions":0,"quantity_free_fbo":2}]

`balanceAfterActApprove`: [{"product_id":"a5b8f909-941f-4ecc-aeee-2a6d95cc51b1","sku_code":"EXTRA-1786785914933","product_name":"Live Extra Product","seller_id":null,"seller_name":null,"packaging_instructions":null,"requires_honest_sign":false,"quantity":1,"quantity_unpacked":1,"quantity_packed":0,"quantity_in_sorting":1,"quantity_in_storage":0,"reserved":0,"available":0,"quantity_fbs":0,"quantity_reserved_directions":0,"quantity_free_fbo":1},{"product_id":"5703d070-f362-4395-ab00-0a3015396c43","sku_code":"PLAN-1786785914933","product_name":"Live Plan Product","seller_id":null,"seller_name":null,"packaging_instructions":null,"requires_honest_sign":false,"quantity":3,"quantity_unpacked":3,"quantity_packed":0,"quantity_in_sorting":3,"quantity_in_storage":0,"reserved":0,"available":0,"quantity_fbs":0,"quantity_reserved_directions":0,"quantity_free_fbo":3}]

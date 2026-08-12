# UI evidence index and architecture adjudication

## Evidence ownership

The orchestrator executed all browser interactions against staging `44fe72e3525332bb01fd76ba420f9cecbdaac6ba` using the mandatory Browser skill and stored PNGs under:

`/Users/deniscivkunov/Projects/WMS/.worktrees/system-review-orchestrator-20260812/docs/reviews/system-wide/runs/2026-08-12/orchestrator/evidence/`

The architect personally opened every image listed below with `view_image`. The stable gate was 1920×1080 CSS pixels, DPR 1. Early 1280 `clicked` captures were also inspected but are interaction evidence only; transitional/black-margin captures are excluded from layout conclusions.

## Stable FF route batch

All files follow `UI-FF-<SCREEN>__synthetic-admin__1920x1080__stable-2s.png`.

| Screen | Visual result | Architecture/state verdict |
|---|---|---|
| `DASHBOARD` | Empty aggregate cards and recent-event panels load | Route/read model only; no state mutation |
| `MP-SHIPMENTS` | Empty document list and seller-owned create control load | Route/read model; separate draft mutation below |
| `FBS` | Empty worklist and WB controls load | Local read model only; no WB action |
| `RECEPTION` | Empty reception queue loads | No inbound state transition proved in browser |
| `SORTING` | Empty sorting queue loads | Sorting-zone process is visible; no putaway mutation |
| `PACKAGING` | Empty task list loads | No packed/unpacked mutation |
| `CELLS` | Empty warehouse list initially loads | Separate durable create/read-back below |
| `SELLERS` | `Review Seller` row loads | Seller-scoped master data visible |
| `CATALOG` | Empty catalog with on-hand/split/reserved/available columns loads | Read-model shape visible; product mutation blocked below |
| `INVENTORY` | Explicit `Раздел в разработке` placeholder | Inventory browser mutation `BLOCKED_BY_PRODUCT_SURFACE` |
| `HONEST-SIGN` | Zero marking counters/list load | No import/issue/print mutation |
| `SETTINGS` | Tenant flags, integrations and staff controls load | Settings surface reachable; authorization mutation not run |

The corresponding twelve `__synthetic-admin__1280x720__clicked.png` files were each inspected. They confirm real clicks but several are cropped or transitional, so they carry no layout verdict.

## Warehouse and cell lifecycle

| Evidence file | Verdict |
|---|---|
| `UI-FF-CELLS__warehouse-create__1920x1080__before-submit.png` | Warehouse form filled before mutation |
| `UI-FF-CELLS__warehouse-create__1920x1080__result.png` | `Review Warehouse 687943` appears after create |
| `UI-FF-CELLS__cell-create-1__1920x1080__before-submit.png` | First `REV-A` cell form filled |
| `UI-FF-CELLS__cell-create-1__1920x1080__result.png` | Post-action screen; later frame provides clearer row evidence |
| `UI-FF-CELLS__cell-create-2__1920x1080__result.png` | Both `REV-A 1.1`, `REV-A 2.2`, generated location barcodes and `Сортировка` visible |
| `UI-FF-CELLS__warehouse-and-cells__1920x1080__reload.png` | Warehouse survives reload, but cells are not in the visible frame |
| `UI-FF-CELLS__warehouse-and-cells__1920x1080__reload-reselect.png` | Intermediate reselect frame still shows only warehouse; insufficient as cell proof |
| `UI-FF-CELLS__warehouse-and-cells__1920x1080__reload-reselect-visible.png` | Corrected frame visibly shows warehouse, both cells/barcodes and sorting location after reload/reselect: durable UI read-back proved |

## Catalog product attempt

| Evidence file | Verdict |
|---|---|
| `UI-FF-CATALOG__product-create__1920x1080__before-submit.png` | Name/SKU/etc. filled, but required seller select is empty |
| `UI-FF-CATALOG__product-create__1920x1080__result.png` | Native `Заполните это поле` validation; dialog stays open |
| `UI-FF-CATALOG__product-create__1920x1080__reload.png` | No created row |

No POST was reached. Source at `FfManualProductCreateDialog.tsx:95-98` blocks empty seller; POST begins at `:115`; non-2xx remains in the dialog at `:120-139`; close occurs only after success at `:141-143`. This batch is not evidence of generic non-2xx masking or close-without-create.

## Marketplace-shipment draft

| Evidence file | Verdict |
|---|---|
| `UI-FF-MP-SHIPMENTS__create-draft__1920x1080__before-submit.png` | `Review Seller` selected, list empty |
| `...__result.png` | Transitional capture; excluded from layout verdict |
| `...__stable-4s.png` | Detail opens as `Отгрузка №000001`, `Черновик`, Review Warehouse/Seller, plan 0 |
| `...__reload.png` | List after reload retains `№000001`, created `12.08.2026 13:24:47`, draft, seller/warehouse, 0 lines |
| `UI-FF-MP-SHIPMENTS__draft-detail__1920x1080__opened.png` | Reopened object has same identity and empty draft state |

This proves durable draft creation and read-back only. It does not prove reservation, packaging, box, WB or shipment transitions.

## Seller identity and portal

| Evidence | Verdict |
|---|---|
| `UI-FF-SELLERS__visual-seller-create__1920x1080__before-submit.png`; `...__result.png` | Seller/account create succeeded and new seller row/notice appeared; result is transitional and excluded from layout verdict |
| `UI-SELLER-FIRST-LOGIN__seller__1280x720__before.png`; `...__set-password.png`; `...__result.png` | Empty-password first-login gate, password-set form and successful seller portal entry were visually proved. Password value is masked |
| `UI-SELLER-DOCUMENTS__existing-test-seller__1920x1080__stable-2s.png` | Documents list loads and shows one MP shipment |
| `UI-SELLER-PRODUCTS__existing-test-seller__1920x1080__stable-2s.png` | WB catalog/FBS stock controls load with zero products |
| `UI-SELLER-HONEST-SIGN__existing-test-seller__1920x1080__stable-2s.png` | Marking inventory loads at zero |
| `UI-SELLER-SETTINGS__existing-test-seller__1920x1080__stable-2s.png` | WB/marking integration presence states load; no credential value is visible |
| `UI-SELLER-DOCUMENTS__discrepancy-action__1920x1080__clicked.png` | CTA returns explicit “will be implemented later” banner; no document/state mutation |

The four seller-empty 1280 loaded files and `UI-SELLER-FIRST-LOGIN__seller__1280x720__result.png` were each inspected. The 1280 settings transitional frame is excluded from layout verdict.

## Seller empty inbound draft

| Evidence | Verdict |
|---|---|
| `UI-SELLER-INBOUND__empty-draft__1920x1080__before-save.png` | Draft date/box count visible with zero product lines |
| `UI-SELLER-INBOUND__empty-draft__1920x1080__result.png` | Documents list contains a new `Поставка` row |

This proves acceptance and same-session list read-back of an empty draft. There is no reload evidence, submit transition, inventory movement or balance change.

## FBS read-only traversal

The architect inspected:

- `UI-FF-FBS__orders-новые__1920x1080__stable.png`;
- `...orders-в-работе...`;
- `...orders-в-доставке...`;
- `...orders-завершённые...`;
- `...orders-отменённые...`;
- `UI-FF-FBS__wb-stocks__1920x1080__stable.png`;
- `UI-FF-FBS__reload__1920x1080__result.png`.

All five order groups are reachable and empty. `В доставке` and `Отменённые` captures have transitional black-margin geometry and are excluded from layout verdict. WB stocks shows `Review Seller` with no active binding. After reload the seller filter resets and controls disable; that proves safe reload of the empty surface, not persistence of the UI filter. No sync/publish/WB mutation was invoked, so FBS mutation remains `BLOCKED_LIVE_WB_NO_SYNTHETIC_INJECTION`.

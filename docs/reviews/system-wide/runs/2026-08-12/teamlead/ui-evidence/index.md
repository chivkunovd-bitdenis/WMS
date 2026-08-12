# UI evidence index — teamlead

All timestamps use MSK. URLs must omit tokens and secret query parameters. Screenshots are full-context captures produced through the Browser skill.

| Scenario / step | URL | Viewport | Time | Test IDs | Action / expected result | File | State evidence |
|---|---|---|---|---|---|---|---|
| TL-AUTH-01 | staging seller portal | 1280×720 result; stable seller routes at 1920×1080 | 2026-08-12 | synthetic seller | Orchestrator completed first password setup and landed in Documents; expected full gate also needs reload, `/auth/me`, and negative role | See seller batch below | Teamlead personally verified images; full scenario remains `NOT_RUN`, environment `BASELINE_BLOCKED`. |
| TL-INV-01 | staging FF Inventory/Catalog | 1920×1080 stable/workflow | 2026-08-12 | synthetic admin/seller | Inventory is placeholder; product attempt rejected because seller unselected | See catalog workflow below | `FAIL` with `TL-F007`; no stock mutation/read-back. |
| TL-DOC-01 | staging FF MP + seller Documents | 1920×1080 | 2026-08-12 | synthetic admin/seller | Create/read draft; expected full lifecycle | See MP/seller workflow below | Draft persistence proved; completion remains `NOT_RUN`. |
| TL-FBS-01 | staging FF FBS | 1920×1080 | 2026-08-12 | synthetic admin | Click all order groups, WB stocks, reload; expected mutation/retry | See FBS batch below | Read-only navigation proved; mutation/retry remains `NOT_RUN`; no WB write. |

## Mandatory FF navigation batch 1

Execution was performed by the orchestrator through the Browser skill on the synthetic staging administrator. Adjudication below was performed independently by the teamlead after opening every named PNG at original detail with `view_image`. The clicked render is evidence that the route was reached; it is not reload/read-back evidence and does not prove the deployed commit because frontend/API/worker/schema versions remain unproven.

Evidence files live in the orchestrator run at `../orchestrator/evidence/`; SHA-256 values below bind this adjudication to the exact images inspected.

| Screen | Evidence / SHA-256 | Teamlead engineering, UX, and runtime verdict |
|---|---|---|
| Отгрузки на МП | `UI-FF-MP-SHIPMENTS__synthetic-admin__1280x720__clicked.png` / `df6647de…0201` | **Clicked render confirmed. UX fail at this viewport:** the content is visibly scaled beyond the available width; the subtitle and the primary create action are cut at the right edge. Seller selection rendered and no loading/error banner is visible, but the lower document state is outside the evidence. No mutation or reload was run. |
| FBS | `UI-FF-FBS__synthetic-admin__1280x720__clicked.png` / `e35a273b…71d8` | **Clicked render confirmed; usable empty-state shell.** Navigation, identity/role, filters, tabs, table header and the explicit “no orders” state are visible without clipping. This proves only a read-only empty worklist. The WB synchronization action was not invoked, so retry/idempotency and WB behavior remain `NOT_RUN`. |
| Приёмка | `UI-FF-RECEPTION__synthetic-admin__1280x720__clicked.png` / `89712ac8…ddc` | **Clicked render confirmed. UX fail at this viewport:** the heading copy and empty-state banner are cut on the right; the user cannot read the full explanation. Runtime returned a coherent “no receptions queued” state and no visible error, but there is no document lifecycle or reload evidence. |
| Сортировка | `UI-FF-SORTING__synthetic-admin__1280x720__clicked.png` / `e43d0121…26f` | **Clicked render confirmed. UX fail at this viewport:** the explanatory copy and empty-state message are horizontally cut. A coherent empty queue is visible, but no active intake, scan, concurrent update, completion, or reload was exercised. |
| Упаковка | `UI-FF-PACKAGING__synthetic-admin__1280x720__clicked.png` / `dfcf2069…29df` | **Clicked render confirmed; blocking visual state.** The application is confined to a narrow central strip while most of the 1280×720 image is darkened; header identity overlaps the left edge and ordinary desktop navigation is not available. An empty task table is visible, but the screenshot does not establish a usable packaging workflow. |
| Ячейки | `UI-FF-CELLS__synthetic-admin__1280x720__clicked.png` / `79e7b646…e7e6` | **Clicked render confirmed. UX fail at this viewport:** the warehouse instruction and table content are cut at the right edge. The visible state says no warehouses exist, so cell creation, selection, stock placement, and reload/read-back remain untested. |
| Селлеры | `UI-FF-SELLERS__synthetic-admin__1280x720__clicked.png` / `ec7a5cc6…32ba` | **Clicked render confirmed. UX fail at this viewport:** only the left portion of the seller card is visible and any controls to the right are inaccessible in the evidence. The synthetic seller name rendered; authorization to open the admin-only page is visually consistent with the displayed administrator role, but no negative-role check or reload was supplied. |
| Каталог | `UI-FF-CATALOG__synthetic-admin__1280x720__clicked.png` / `06fab567…12a5` | **Clicked render confirmed; desktop content usable in the captured image.** Filters, create/import actions, table columns and an explicit empty catalog state render without an error. The full-page PNG is 1727 px wide despite a declared 1280 px viewport, which is direct evidence of horizontal document overflow. No product mutation or read-back occurred. |
| Инвентаризация | `UI-FF-INVENTORY__synthetic-admin__1280x720__clicked.png` / `b1ba399d…9bf5` | **Clicked render confirmed; product gap visible.** The route contains only “Раздел в разработке” and exposes no inventory operation. The content is also oversized for the viewport. Therefore this screen cannot satisfy the mandatory inventory mutation; an alternative existing operations screen is still required. |
| Честный знак | `UI-FF-HONEST-SIGN__synthetic-admin__1280x720__clicked.png` / `743f3ee3…fe4ae` | **Clicked render confirmed; blocking visual state.** The main application is narrowed and surrounded by a dark overlay/background; header identity overlaps the left edge. Summary counters and the synthetic seller filter rendered with zero values, but the lower content is cut and no import, ledger, reprint, or reload was exercised. |
| Настройки | `UI-FF-SETTINGS__synthetic-admin__1280x720__clicked.png` / `6237ba7f…3921` | **Clicked render confirmed; usable settings shell.** Address storage and print controls, payroll month, empty employee state, and add-user form render coherently. The copy explicitly says that a newly added employee creates a password on first login; this is corroborating UI evidence for the separately reviewed initial-password security boundary, not proof of exploitation. No setting was changed. |
| Дашборд | `UI-FF-DASHBOARD__synthetic-admin__1280x720__clicked.png` / `055ce1c4…153b` | **Clicked render confirmed. UX fail at this viewport:** dashboard cards and explanatory text run beyond the right edge; the 1280×1288 full-page image still does not expose the complete horizontal content. Empty inbound/planned-shipment summaries are visible and no runtime error is shown. |

Batch verdict: **12/12 screenshots personally adjudicated; 12/12 routes clicked; 0/12 reload/read-back checks in this batch.** The early clicked frames are retained only as transition evidence. The later stable 1920×1080 batch is authoritative for desktop layout. `Инвентаризация` is visibly a placeholder. The route render evidence is staging-only and is not attributed to baseline `a39530c` while the deployment-version gate is blocked.

## Stable FF desktop batch

Execution: orchestrator Browser, synthetic staging administrator, `window.innerWidth=1920`, `innerHeight=1080`, DPR `1`, two-second stabilization. Adjudication: teamlead personally opened all 12 original PNGs. The stable batch supersedes the dark/narrow transitional presentation seen in some early clicked frames.

| Screen | Evidence / SHA-256 | Independent verdict |
|---|---|---|
| Dashboard | `UI-FF-DASHBOARD__synthetic-admin__1920x1080__stable-2s.png` / `263c7e4b...e1d` | Stable shell and coherent empty summaries render, but the content still runs beyond the right image edge. |
| MP shipments | `UI-FF-MP-SHIPMENTS__synthetic-admin__1920x1080__stable-2s.png` / `07a40a6e...a32` | Form, selector and empty table render; right-side table/action content remains clipped. |
| FBS | `UI-FF-FBS__synthetic-admin__1920x1080__stable-2s.png` / `ff8a61e7...1d1` | Stable empty worklist renders, while the right end of the page is outside the viewport. |
| Reception | `UI-FF-RECEPTION__synthetic-admin__1920x1080__stable-2s.png` / `6706c6a3...daf` | Empty queue is coherent; explanatory text is clipped on the right. |
| Sorting | `UI-FF-SORTING__synthetic-admin__1920x1080__stable-2s.png` / `7251237e...27a` | Empty queue is coherent; explanatory text is clipped on the right. |
| Packaging | `UI-FF-PACKAGING__synthetic-admin__1920x1080__stable-2s.png` / `b71df787...e33a` | Stable table replaces the earlier transition frame; introductory content remains clipped. |
| Cells | `UI-FF-CELLS__synthetic-admin__1920x1080__stable-2s.png` / `e4cad2cd...270` | Stable empty state; later mutation batch supplies durable evidence. |
| Sellers | `UI-FF-SELLERS__synthetic-admin__1920x1080__stable-2s.png` / `969d2efb...c896` | Seller row renders; right portion remains outside the image. |
| Catalog | `UI-FF-CATALOG__synthetic-admin__1920x1080__stable-2s.png` / `da5d9caf...a7bd` | Empty catalog and controls render, with table/action content extending right. |
| Inventory | `UI-FF-INVENTORY__synthetic-admin__1920x1080__stable-2s.png` / `b020c0f3...e4b1` | Only `Раздел в разработке`; no inventory operation exists on the route. |
| Honest Sign | `UI-FF-HONEST-SIGN__synthetic-admin__1920x1080__stable-2s.png` / `22727b91...12ac` | Stable counters/actions replace early transition frame; right content is clipped. |
| Settings | `UI-FF-SETTINGS__synthetic-admin__1920x1080__stable-2s.png` / `91c15f48...1fcb` | Stable settings shell and employee controls render; lower content needs scroll and right text is clipped. |

Stable batch verdict: **12/12 personally adjudicated.** All routes load without a visible fatal error. Eleven present actual content; Inventory is a product placeholder. A shared horizontal overflow is visible even at a verified 1920 CSS pixels.

## Warehouse/cell and catalog mutation batch

Execution: orchestrator Browser. Adjudication: teamlead opened all nine original workflow PNGs plus the corrected durable cell proof.

- Warehouse/cell sequence: `warehouse-create before/result`, `cell-create-1 before/result`, `cell-create-2 result`, reload, and corrected reload/reselect proof. Dialogs are visually cut on the right/bottom. The result shows warehouse `Review Warehouse 687943`, cells `REV-A 1.1`, `REV-A 2.2`, and the sorting row. `UI-FF-CELLS__warehouse-and-cells__1920x1080__reload-reselect-visible.png` / `e70da197...bf2d` proves all four persisted after reload/navigation and warehouse reselection. This is a durable warehouse-configuration mutation, not a stock-quantity mutation.
- Product sequence: `UI-FF-CATALOG__product-create__1920x1080__{before-submit,result,reload}.png` / `c9065953...4357`, `c1fc63d3...e66a`, `06c1bb16...1b45`. Seller was not actually selected. Native required-field validation kept the dialog open, and reload showed no product. This is a correctly rejected validation attempt, not evidence of a generic API-error path and not a successful inventory mutation.
- Static cross-check: both `44fe72e` and `a39530c` contain `setError(raw); return` for unrecognized product-create non-2xx responses. The proposed generic fall-through defect is therefore **refuted for both compared SHAs**.

## Seller portal batch

Execution: orchestrator Browser. Adjudication: teamlead opened all five requested 1280 captures and all four stable 1920 captures.

| Route | Stable evidence / SHA-256 | Verdict |
|---|---|---|
| First login result | `UI-SELLER-FIRST-LOGIN__seller__1280x720__result.png` / `26d0bfd4...240d` | Password setup led to authenticated Documents. This proves a successful role-aware landing, not a negative-role authorization test. |
| Documents | `UI-SELLER-DOCUMENTS__existing-test-seller__1920x1080__stable-2s.png` / `4f03b7f5...4f33` | Existing outbound row renders. The third primary action is clipped at the right. |
| Products | `UI-SELLER-PRODUCTS__existing-test-seller__1920x1080__stable-2s.png` / `a7070ea8...7369` | FBS explanation and empty product table render; wide content continues beyond the viewport. |
| Honest Sign | `UI-SELLER-HONEST-SIGN__existing-test-seller__1920x1080__stable-2s.png` / `21f149a8...02c9` | Counters, upload and ledger controls render; right counter is clipped. |
| Settings | `UI-SELLER-SETTINGS__existing-test-seller__1920x1080__stable-2s.png` / `486a69f7...56d` | Stable settings integration cards render. The earlier 1280 Settings capture was transitional and is not used for layout. |

The discrepancy action capture `UI-SELLER-DOCUMENTS__discrepancy-action__1920x1080__clicked.png` / `976394e3...c6b9` shows an explicit message that the action is deferred to a future stage. The empty inbound-draft before/result pair (`d9a938ed...0311`, `5011b715...e59d`) shows a new `Поставка` row after save, but no reload capture was supplied, so durable seller-document read-back remains incomplete.

## FF marketplace-shipment draft lifecycle

The orchestrator created an empty MP shipment draft, allowed the stable list to render, reloaded, and reopened it. Teamlead personally opened all five images: `before-submit` `07a40a6e...a32`, `result` `93047989...e1be`, `stable-4s` `2d117bc0...1e63`, `reload` `a209160c...9830`, and `draft-detail` `320d4c9b...6ff3`. Draft `№000001`, seller and warehouse survive reload and reopen. This proves **draft creation/read-back only**, not submit→packing→shipping completion.

## FBS read-only operator path

Execution: orchestrator Browser, no WB mutation. Teamlead personally opened `Новые`, `В работе`, `В доставке`, `Завершённые`, `Отменённые`, `Остатки WB`, and reload images (hashes `72f33805...136f`, `1ac0e012...5378`, `fe815589...13f5`, `c52503e0...ef31`, `5d8b2c46...1524`, `a8a8f333...e91a`, `36b84ea6...d41a`). All tabs load coherent empty/read-only states and reload returns to a usable Orders shell. Several intermediate captures are transitional narrow/dark frames; stable New/Completed/WB-stock frames establish the actual layout. Because no order, supply, retry, ambiguous response, or WB write was exercised, FBS retry/idempotency remains `NOT_RUN` at runtime.

# S05 PROCESS_MAP - BLG-KC01

## Source and decomposition rule

Backlog item: `BLG-KC01` - Развернуть клиентские входящие по приёмке, навигации, остаткам, отгрузке и печати.

Business meaning is preserved in full: fourteen independent client requirements must become fourteen atomic discovery/contract tracks before Dev. They may share a later screen or data source, but none may be merged, silently dropped, or treated as an implementation detail of another item. This S05 map records the operational result and the questions handed to S06; it does not assert unverified current code, API, marketplace, or production facts.

## Process variants

### KC-01 - Red seller-document badges

- **Actor and action:** a fulfilment employee scans shared reception and shipment lists and opens the newly created seller document that needs attention.
- **Document/data:** seller-originated document, its lifecycle/attention marker, and a per-list visible counter; the counter is not a defect, discrepancy, or item-quantity counter.
- **Success:** each relevant list makes new or attention-required seller work visible with a red count or `1`; opening/acknowledging the document updates the visible work without hiding unrelated documents.
- **Empty/error/repeat/cancel:** no qualifying document means no badge (or an explicit zero only if the local canon requires it); unavailable list data shows a recoverable loading/error state, never a fabricated zero; refresh and repeated acknowledgement do not double-count; leaving the list performs no acknowledgement.
- **S06 handoff:** identify each shared list, the authoritative seller-origin and attention transition, acknowledgement semantics, API fields, and whether unread state is per user or organisation.

### KC-02 - Reception progress by physical boxes

- **Actor and action:** a reception operator confirms boxes and uses the screen to see received boxes against boxes expected in the inbound document.
- **Document/data:** inbound/reception document, declared box count, accepted-box identities/statuses, and the derived `accepted / expected` progress.
- **Success:** the reception screen presents the box ratio alongside line quantities and recalculates after every successful box confirmation.
- **Empty/error/repeat/cancel:** a document with no declared boxes states that box progress is unavailable/not applicable rather than `0 / 0`; a failed confirmation retains the last confirmed ratio and explains the retry; replaying the same confirmation is idempotent; cancelling an unconfirmed step does not change progress.
- **S06 handoff:** find the source of expected boxes, identity/idempotency rules for accepted boxes, reception screen boundary, and treatment of partial or amended documents.

### KC-03 - Physical warehouse selection at reception

- **Actor and action:** a reception operator assigns arriving stock to its physical warehouse before receipt is finalised.
- **Document/data:** organisation, active accessible physical warehouses, selected warehouse, and the resulting inventory placement; service/FBS warehouses are not interchangeable with physical receipt destinations.
- **Success:** multiple eligible warehouses require a clear selection that is persisted with receipt; exactly one eligible physical warehouse is selected automatically without needless confirmation.
- **Empty/error/repeat/cancel:** no eligible warehouse blocks final receipt with an actionable explanation; failed list load cannot default silently; reopening/retrying preserves a prior valid selection; cancelling leaves stock unreceived and creates no placement.
- **S06 handoff:** establish eligibility, permissions, single-warehouse auto-selection, persistence point, and relationship to KC-05 filtering and stock/reserve accounting.

### KC-04 - Logo returns to home safely

- **Actor and action:** an operator on a main application section uses the logo to return to the home page.
- **Document/data:** current route, target home route, and page dirty-state/navigation guard where a form has unsaved changes.
- **Success:** logo activation from every main section opens the home page, causes no business mutation, and does not discard modified form data without the same confirmation used for other exits.
- **Empty/error/repeat/cancel:** an already-home route is a harmless no-op; unavailable routing reports the existing navigation error rather than changing data; repeated clicks create no duplicate navigation side effect; choosing "stay" in a discard prompt keeps the operator on the original form.
- **S06 handoff:** inventory all main-section shells/logo consumers, define the canonical home target, and bind this navigation to KC-06 dirty-form detection.

### KC-05 - Hide FBS warehouses in general warehouse choices

- **Actor and action:** an operator chooses or views a warehouse in ordinary inventory, reception, and general-list workflows.
- **Document/data:** warehouse catalogue, warehouse kind/flag, general context versus explicitly FBS-specific context, and any filter state.
- **Success:** general lists and selectors exclude service FBS warehouses by default; FBS workflows or an explicit relevant filter retain access where the technical warehouse is required.
- **Empty/error/repeat/cancel:** no physical warehouse produces a truthful empty state, not a substituted FBS choice; a classification/load error must not expose a misleading mixed list; refreshing/reapplying the default does not change selection; cancelling filters restores the prior valid view without changing data.
- **S06 handoff:** locate the authoritative FBS classification and all general/FBS-specific consumers; reconcile shared selection rules with KC-03 and KC-11.

### KC-06 - Confirm exit from unsaved changes

- **Actor and action:** an operator edits a reception or other work form, then tries to close it, press Escape, click outside a dialog, or navigate away.
- **Document/data:** form baseline, dirty-state calculation, save result, navigation/close event, and discard-confirmation choice.
- **Success:** every listed exit path recognises meaningful unsaved edits and offers "stay and continue" or deliberate discard; a successful save clears dirty state.
- **Empty/error/repeat/cancel:** untouched forms leave without a prompt; failed save leaves the form dirty and visible with retry guidance; repeated exit attempts do not stack dialogs or lose edits; cancelling/discard denial always returns to the same editable state.
- **S06 handoff:** enumerate form containers and exit mechanisms, define what constitutes a meaningful change, and identify the reusable guard needed also by KC-04.

### KC-07 - One stock pool across warehouses

- **Actor and action:** an inventory manager allocates available stock among warehouses while marketplace availability and reservations rely on the same physical pool.
- **Document/data:** physical on-hand quantity, reservations, per-warehouse allocations, allocation total, available remainder, and the transaction/version used to protect concurrent updates.
- **Success:** sum of active allocations/reservations cannot exceed the confirmed physical pool; the operator can see assigned quantity per warehouse and remaining allocable stock before saving.
- **Empty/error/repeat/cancel:** zero stock permits no positive allocation; stale/conflicting updates are rejected with refreshed values, not overwritten; retrying a completed allocation does not reserve twice; cancelling an edit leaves prior allocations intact.
- **S06 handoff:** map current inventory/reserve ownership, consistency boundary and concurrency rules, downstream marketplace availability, and how physical versus FBS warehouses from KC-05 participate.

### KC-08 - Scanned shipment quantity cannot be manually raised

- **Actor and action:** a shipment operator works in scan mode; each accepted scan records the physical item in hand, while permitted undo removes a prior scan.
- **Document/data:** shipment/order, scan-mode flag, scanned-item event/identity, derived quantity, manual-entry capability, and undo/audit trail.
- **Success:** in scan mode quantity changes only after a successful scan or an authorised undo of a recorded scan; normal manual quantity editing is unavailable.
- **Empty/error/repeat/cancel:** an unrecognised, duplicate, or non-shipment scan changes no quantity and explains why; failed scanner/API processing preserves the last accepted total; retrying the same scan follows idempotency rules; cancelling scan mode does not invent or remove counted goods.
- **S06 handoff:** identify scan-mode entry points, item identity and duplicate policy, permitted undo roles, API validation, and coverage for non-scan workflows that may retain controlled manual entry.

### KC-09 - Box cell is not mandatory for shipment

- **Actor and action:** a shipment operator creates or completes a box for an already assembled shipment without being blocked by an unrelated storage-cell requirement.
- **Document/data:** shipment box, optional storage-cell reference, box completion validation, and separate location data for search, putaway, and picking.
- **Success:** a box can be completed and shipment can proceed without a cell; when present, a cell remains informational/location data and is not erased by this change.
- **Empty/error/repeat/cancel:** an empty cell is accepted only in the box/shipment context; invalid supplied cell receives a clear validation error; repeating completion does not create a second box effect; cancelling retains the draft without a mandatory-cell error.
- **S06 handoff:** find every validation schema/UI/API boundary requiring a box cell and distinguish them from workflows where a location remains truly required, including KC-11.

### KC-10 - Shipment calendar displays real load

- **Actor and action:** a fulfilment planner views a calendar period, sees planned shipments on their dates, and opens the selected day's shipment document.
- **Document/data:** calendar range/timezone, eligible shipment dates/statuses, API query/result, UI event rendering, and document link.
- **Success:** real eligible shipments appear on the correct days; selecting a day provides the related document; a genuinely empty period is explicitly explained.
- **Empty/error/repeat/cancel:** distinguish an empty API result from query/API/render failure; loading or failure never masquerades as an empty period; refreshing the same range does not duplicate events; cancelling range/filter changes keeps the prior displayed period.
- **S06 handoff:** trace data source through query and UI rendering, define date/status/timezone rules, document-opening route, and diagnostic evidence needed to locate the current blank-calendar cause.

### KC-11 - Goods-by-cell list

- **Actor and action:** a warehouse employee searches from a product to its current cells or from a cell to its stored goods for picking and inventory work.
- **Document/data:** product identity, cell identity, quantities/currentness, normal versus service storage-zone marker, search/filter criteria, and access scope.
- **Success:** a list/report supports both search directions, shows current quantity, and visibly distinguishes ordinary from service zones without conflating them.
- **Empty/error/repeat/cancel:** no match states which search yielded no current placement; stale/unavailable location data is reported rather than guessed; repeating a search yields a stable result for the same snapshot; clearing/cancelling filters returns to the defined base list without altering inventory.
- **S06 handoff:** locate inventory-location source and freshness rules, product/cell search contract, zone taxonomy, permissions, and interplay with optional box cells in KC-09 and FBS filtering in KC-05.

### KC-12 - Send product barcodes to Wildberries

- **Actor and action:** a fulfilment operator submits a WB supply; WMS prepares product barcodes and records the marketplace result without exposing credentials.
- **Document/data:** supply, product barcode source/normalisation, WB API's verified current request contract, request/response status, safe correlation/audit record.
- **Success:** after contract discovery, the request contains the correct barcode field(s) and format for every eligible product; accepted/rejected WB outcome is visible and recoverable to the operator.
- **Empty/error/repeat/cancel:** missing or invalid barcode blocks/flags the affected product before an unsafe request; unavailable/rejected WB response preserves an explainable pending/failure state; retries follow a confirmed idempotency/replay policy; cancelling before submission sends nothing.
- **S06 handoff:** locate barcode source and existing WB submission seam, classify this as external-contract discovery, and specify redacted request/response evidence plus no-secret handling before S07/S13 implementation planning.

### KC-13 - Excel shipment upload to Wildberries

- **Actor and action:** a fulfilment operator prepares a box-level WB shipment file, validates it, uploads through a supported WB path, and sees whether WB accepted it.
- **Document/data:** shipment boxes/orders, WB-supported Excel template and version, required/optional fields and limits, generated/selected file, validation report, upload result, and safe correlation record.
- **Success:** only after discovery confirms the live contract, the operator can produce/choose a compliant file, correct validation errors, submit it, and see the final accepted or rejected outcome rather than manually re-entering each item.
- **Empty/error/repeat/cancel:** no boxes/orders explains why no file can be formed; template/field/file/upload errors name the repairable rows/fields without leaking sensitive data; retry is allowed only under a confirmed duplicate-submission policy; cancelling generation or upload leaves the underlying shipment unchanged.
- **S06 handoff:** separate WB contract research from possible MP Fit reuse, determine file ownership/generation versus upload responsibility, required evidence and test fixture, and any owner decision before live marketplace use.

### KC-14 - One order for QR labels and pick sheet

- **Actor and action:** a picker prints QR labels and the corresponding pick sheet, then matches each label to the same ordered position without manual searching.
- **Document/data:** one selected order set, leading sort key/direction, QR-label renderer input, pick-sheet renderer input, printed sequence, and test fixture comparing both outputs.
- **Success:** both artefacts derive their item order from the same explicit sorting rule for the same order set, so position-to-label matching is consistent.
- **Empty/error/repeat/cancel:** an empty eligible set produces a clear no-print state; renderer/data failure produces no partial misleading print and identifies the failed artefact; reprint with unchanged input retains order; cancelling before print emits no labels or sheet.
- **S06 handoff:** find both render pipelines and their existing sort keys, choose the authoritative ordering owner, determine print atomicity/partial-output behaviour, and define a common fixture/assertion.

## Cross-item boundaries and S06 input

S06 must create an atomic card and contract/test cases for every `KC-01` through `KC-14`; a later technical dependency may link cards but may not collapse their business outcomes. The analysis must first establish actual screen, API, schema, and integration boundaries. In particular: KC-03/KC-05/KC-07/KC-11 share warehouse concepts but have different operator decisions; KC-04/KC-06 share navigation protection but retain separate outcomes; KC-08/KC-09/KC-10/KC-12/KC-13/KC-14 each governs a different shipment or marketplace action.

No implementation decision is authorised here. Current production state, live WB contract, marketplace response, secrets, and release SHA remain unknown until their specifically authorised discovery stages.

## Out of scope

No app code, deploy, production-data change, live WB/Ozon call, secret/key operation, merge, push, or release action.

## S05 verdict

`PROCESS_MAP_READY`: all fourteen client items are independently mapped with operational states and S06 discovery boundaries. The next stage may perform the gap analysis; it must not claim that any item is Dev-ready before its own contract, research, and test evidence exist.

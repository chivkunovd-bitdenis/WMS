# Data flow notes (MP unload / boxes)

> Актуальная модель процесса (2026-06-28): [`analysis/01_normalized_process_spec.md`](analysis/01_normalized_process_spec.md), задачи — [`analysis/06_mp_unload_unified_tasks_RU.md`](analysis/06_mp_unload_unified_tasks_RU.md).

## Product TZ Excel import with declared stock

1. FF admin uploads `.xlsx`; importer scans workbook sheets in order and uses only the **first** sheet whose headers match the product TZ structure.
2. Optional **«Кол/во, заявленное клиентом»** is validated per product row. Preview returns each `declared_quantity` and the valid-row `declared_total`.
3. Apply re-runs preview. If positive quantity exists, the tenant must have exactly one warehouse; its virtual `__SORTING__` location is selected automatically.
4. Product matching remains tenant + seller + barcode. Existing product is updated; missing product is created; barcode owned by another seller remains a row error.
5. Every positive quantity is recorded through `inventory_service.record_movement_and_adjust_balance` with movement type `product_tz_import`. All balance bucket mutations are database-atomic and interoperate on the same row: positive receipt uses upsert, packaging uses a conditional bucket-transfer `UPDATE`, and deduction uses a conditional preference-aware `UPDATE`. Concurrent import + package/deduct cannot overwrite each other; `quantity = quantity_unpacked + quantity_packed` remains true.
6. Products, movements, balances, and the import idempotency record commit in one transaction. Any unignored row error or apply failure rolls the whole transaction back.
7. SHA-256 of uploaded bytes is protected by a DB unique constraint scoped by tenant + seller + warehouse scope + import type. Only a conflict on that named constraint is interpreted as `already_applied`; unrelated integrity failures propagate. Reapply returns `already_applied=true`, zero added quantity, and zero movements.

## Product availability for MP unload pickers

- Readonly `GET /operations/marketplace-unload-requests/available-products` is the single picker source for seller and FF portals.
- Formula is the MP domain formula: **storage + sorting − operational outbound reserves − other active MP unload reserves**. Active MP reserve statuses come from the shared `marketplace_unload_status.RESERVE_STATUSES` contract used by both marketplace and inventory services and include `submitted`, `confirmed`, and `collecting`.
- When editing an existing MP unload, `exclude_request_id` removes that request’s own reserve from the subtraction.
- Tenant, seller, and warehouse scope are checked on the backend. Seller users cannot request another seller’s products.
- The global inventory summary is intentionally unchanged: its `available` remains storage-only, and internal outbound reservation behavior is unchanged.
- Seller and FF clients discard late detail/availability responses after the dialog/request scope changes. Product TZ preview and apply use independent request sequences; seller/file controls are disabled during apply, and a response from a closed/reopened dialog cannot reset, notify, or close the new dialog.

## Document lifecycle (FF marketplace unload)

| Status | Meaning | Packaging task | Boxes / collect |
|--------|---------|----------------|-----------------|
| `draft` | FF or seller edits plan | **None** | Blocked |
| `submitted` | Seller planned | **None** | Blocked |
| `confirmed` | FF confirmed | Created on confirm (full plan) | Allowed |
| `collecting` | First box or first line in box | Progress counter only | Allowed (parallel with packaging) |
| `shipped` | Stock written off | Must be `done` | Distribution complete for ship |
| `cancelled` | Rolled back | Unlinked | Cleared |

- UI: **2 tabs** — «Товары» (lines, boxes, WHB scan, footer ship) and «Упаковка» (linked `PackagingTask`).
- **Ship gate:** `assert_unload_packaging_done` on backend; UI disables **«Отгружено»** until `linked_packaging_task.is_complete` and at least one unit distributed to boxes.

## Collect into box

- Stock is reserved on confirm; **deducted from cell** (or sorting zone when address storage off) when lines are added to MP unload boxes via modal / scan / attach.
- Main scan on «Товары» accepts **WHB/INB only** (ready box attach); cell/product scans use the box add modal.

## Cancel unload (`POST .../cancel`)

- Deletes pick allocations and box lines for the request.
- Returned quantity goes to the **sorting zone** virtual `StorageLocation` (DEC-018), **not** back to the original collect cells.
- Total warehouse stock is restored; only the allocation location changes (sorting buffer).
- See `marketplace_unload_collect_service.py` — `_return_picked_to_sorting_on_cancel`.

## Copy box (`POST .../boxes/{id}/copy`)

- Creates a **new closed** marketplace unload box (`closed_at` set immediately).
- Lines are re-collected from existing pick allocations (same plan limits as manual add).
- **Add products** is blocked on copied boxes (`box_closed`) — by design: copy is a sealed duplicate for labels/repeat shipment, not an editable open box.
- For editable open boxes use `POST .../boxes/batch` (open boxes, `closed_at=NULL`).

## Address storage toggle (DEC-019)

- `PATCH /tenant/settings` with `address_storage_enabled: false` triggers `migrate_all_address_balances_to_sorting` — all qty from address cells → virtual sorting location atomically.
- FF settings UI shows info alert after successful disable.

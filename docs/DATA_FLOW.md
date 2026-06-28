# Data flow notes (MP unload / boxes)

> Актуальная модель процесса (2026-06-28): [`analysis/01_normalized_process_spec.md`](analysis/01_normalized_process_spec.md), задачи — [`analysis/06_mp_unload_unified_tasks_RU.md`](analysis/06_mp_unload_unified_tasks_RU.md).

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

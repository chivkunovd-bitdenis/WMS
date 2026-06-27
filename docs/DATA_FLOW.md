# Data flow notes (MP unload / boxes)

## Cancel unload (`POST .../cancel`)

- Deletes pick allocations and box lines for the request.
- Returned quantity goes to the **sorting zone** virtual `StorageLocation` (DEC-018), **not** back to the original collect cells.
- Total warehouse stock is restored; only the allocation location changes (sorting buffer).
- See `marketplace_unload_collect_service.py` — `_return_picked_to_sorting_on_cancel`.

## Copy box (`POST .../boxes/{id}/copy`)

- Creates a **new closed** marketplace unload box (`closed_at` set immediately).
- Lines are re-collected from existing pick allocations (same plan limits as manual add).
- **Add products** is blocked on copied boxes (`box_closed`) — by design: copy is a sealed duplicate for labels/repeat shipment, not an editable open box.
- For editable open boxes use `POST .../boxes/batch` (REV-FIX-002).

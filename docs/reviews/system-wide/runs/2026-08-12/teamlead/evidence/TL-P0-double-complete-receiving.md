# Sanitized evidence card — concurrent complete-receiving

- Executed by: teamlead, independently of the architect tenant and IDs.
- Target: staging API; no WB request and no shared tenant/data.
- Method: two fresh synthetic tenants, each with its own warehouse, product and inbound document. Each document had one line with `expected_qty=1`; one receiving scan established `actual_qty=1`. Two separate HTTP clients then started `POST .../complete-receiving` concurrently.
- Secret boundary: generated email, password, bearer token, tenant/document/product/warehouse UUIDs and complete response bodies were neither printed nor retained in this artifact.
- Cleanup boundary: no safe tenant-delete API was available and deleting the corrupted ledger would destroy evidence. The two isolated synthetic tenants were not reused or shared; no WB/external data was created.

## Attempt TL-P0-A

- Precondition read-back: request `receiving`; scan fact `1`.
- Concurrent responses: request A `HTTP 200`, document state `sorting`; request B `HTTP 200`, document state `sorting`.
- Final document read-back: state `sorting`, `actual_qty=1`, `posted_qty=0`, `sorting_remaining_qty=1`.
- Inventory summary read-back for the isolated product: total `2`, in sorting `2`, in storage `0`.
- Movement read-back: exactly two `inbound_intake` rows; deltas `[+1, +1]`; sum `+2`.

## Attempt TL-P0-B

- Precondition read-back: request `receiving`; scan fact `1`.
- Concurrent responses: request A `HTTP 200`, document state `sorting`; request B `HTTP 200`, document state `sorting`.
- Final document read-back: state `sorting`, `actual_qty=1`, `posted_qty=0`, `sorting_remaining_qty=1`.
- Inventory summary read-back for the isolated product: total `2`, in sorting `2`, in storage `0`.
- Movement read-back: exactly two `inbound_intake` rows; deltas `[+1, +1]`; sum `+2`.

## Independent verdict

Attempts / reproduced: **2 / 2**. The document fact remains one unit while the stock ledger and balance contain two. The second request is not rejected or reconciled; both callers receive success.

The orchestrator identified the staging deployment as commit `44fe72e3525332bb01fd76ba420f9cecbdaac6ba`. The teamlead did not derive that SHA from a public application version surface. Static comparison proves that `44fe72e` is an ancestor of etalon `a39530c` and that the three critical paths (`inbound_intake_service.py`, `inbound_intake.py`, `inventory_service.py`) are byte-identical between those commits. The etalon therefore contains the same code-level race even though the staging SHA attribution depends on the orchestrator deployment manifest.

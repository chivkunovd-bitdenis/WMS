# WMS-675 · exact14 stale reserve projection: actual repair

## Authority and preconditions

This is the one authorised data repair after accounting recovery `f0411289b`;
it is not a second WMS-662 handoff. The operational script was committed before
execution in `f6b7129258f333f62b22cb8e4a0722e06c8d9adc`.

Fresh production preflight is preserved in
[PRE_APPLY_FRESH_READ_RECEIPT.json](PRE_APPLY_FRESH_READ_RECEIPT.json). It
proved the exact tenant/seller/WMS supply/warehouse, 31 positions, and only the
known 14 `done` positions with projection `reserved_quantity=1`. Both actual
reservation tables were empty. Journal targets and completed ledger were 26,
reversal was zero, and `missing_delta=0`. Facts/charges were 26/52 with the
pre-existing ID-set hashes.

## Applied operation

At `2026-10-07T07:02:23.522940+00:00` the script acquired existing
`lock_order_batch_packaging_rows` and `lock_handoff_batch_products`, reloaded
all guards inside the transaction, then changed exactly the 14 stale Ozon
position projections to zero through SQLAlchemy model instances and set their
ordinary reserve state to `released`. The one commit returned at
`2026-10-07T07:02:24.431622+00:00`.

It did not call `conduct_supply`, observation persistence, billing, inventory
movement, marketplace transport, seller sync, stock publication or a manual
SQL `UPDATE`. On a lost commit reply the script was specified to stop and read
back before any retry; a reply was received, and no retry occurred.

## Independent readback

[POST_APPLY_INDEPENDENT_READBACK.json](POST_APPLY_INDEPENDENT_READBACK.json)
is a new `REPEATABLE READ, READ ONLY` application session at 07:04:05 UTC. It
confirms all 31 projections are zero, both actual reservation tables remain
empty, all 31 reserve states are `released`, journal remains 31/26, ledger is
26 completed with no reversal, and `missing_delta=0`.

Facts (26) and charges (52) have the same pre/post ID-set hashes. The readback
also found no inventory movement created since repair start and records the
current six-row balance and linked-movement hashes. A pre-apply balance hash
was not recorded by the operational script, so this report intentionally does
not claim a literal before/after balance-hash comparison. The committed code
only assigned `FbsOrderProduct.reserved_quantity` and `FbsOrder.reserve_status`
after its locked checks; it did not invoke any stock-mutating service.

## Result and limitation

**WMS-675 accounting restored and reserve cache cleaned.** The exact recovery
scope now has zero actual reserve rows, zero stale position projection, ledger
delta zero, and unchanged financial ID sets.

The permanent service correction `8bf5b41a0` remains a follow-up code release;
it is not claimed as deployed by this one-shot data repair. The production
runtime was not patched or reconfigured.

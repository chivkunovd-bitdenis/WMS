# WMS-675 fresh addressed read-only evidence,2026-10-07

**Fresh snapshot missing14 units, not historical26. No conduct/write performed by collector.**
Branch codex/wms675-fresh-readonly-20261007 starts from published production proof
1c8810bff603b63ea1e12e07df1b5fc76828df52. Actual producer checkout/API relevant source
verified4c532f0cccfb8f99b34d68d9630a3763038fbc5f. Installed observed-handoff/provider/
transport/account-service hashes match exact4c; source/copy receipts preserved.

Exact scope: tenant b80a893b-ab87-42b6-8fd7-6d41502c900f, seller
cf6d31c5-944b-4382-af34-636ca9aa8cc3, draft
b82d1e9a-30d2-4d7b-b52d-9775c3d266e3, warehouse
2d968c65-4a8d-414e-9076-0f201c2dba63, sorting
7d44fbc9-9c82-4ef1-bac7-4e47fe5de3c1.

Executed unchanged published collect_current_accounting.py through NORMAL local
support-agent load_config/private ProdSql settings and existing exact tenant-role.
All11 original SELECTs succeeded, actual reader exit0; identity READ ONLY/RLS on.
No ensure/grants/role/schema change. Accounting UTC06:26:39–06:26:58; each SQL/output
hash/status/count saved. Separate snapshots, not a common transaction.

Executed unchanged published collect_ozon_bound.py+ozon_read_plan.json through
normal SSH/default identities/docker exec in installed /app of wms_prod-api-1.
Only these two published files copied into a private own container temp; hashes
match independently reviewed reader77f56f1100d27db0f369ff7edb436332c9fd91f295d4065c90bcb51e68e80011
and seedcccfb2d7c024f02309f23424a67473723cfcb6d7d85312f138f1b152e04bc00b.
Existing account service used credentials internally; no credential transfer/dump.
Normal application business settings unchanged; PYTHONPATH=/app only selects the
installed package as in the published invocation. No flags/monkeypatch/retry.
Reader exit0, UTC06:29:01–06:29:07:31/31 HTTP200,unknown0,children0,unread0.
HTTP POST /v3/posting/fbs/get is semantic read, concurrency1, maximum124 unique
cards (only31 seeds requested in this run). Sanitized allowlist only; no raw API
response/customer/auth/body/headers stored. Plan/input/copy/execution hashes saved.

Composition31 is unchanged: exact order/position/product/seller/SKU/offer/quantity
and warehouse match seed, accounting and fresh backend scope snapshot. Each has
quantity1. Fresh statuses14 delivered/posting_received,12 delivering,5 cancelled.
Four status changes from old plan:0148656673-0134-1 awaiting→cancelled;0187441457-
0073-1,56845110-0045-1,83893932-0680-2 delivering→delivered. All five cancels
excluded; no parent/child duplication. No composition/unknown/reversal conflict
found in these snapshots. This does not bypass fresh native lock/recheck.

Completed quantities use exact4c completed_quantities semantics: nonreversed ledger
recipe quantities with movement_id (fallback only to shipment_movement_id if no
recipes).31 current ledgers,12 linked expenses/written_off,0 reversal; target history
independently attributes12 movements/delta-12. Fresh positive proof26 minus already
conducted12 gives14 missing. Full per-position exact IDs/proofs/links in
missing-recalculation.json.

| SKU | Fresh proved | Already conducted | Missing | Current sorting/balance |
| --- | ---: | ---: | ---: | ---: |
|1586484429|4|2|2|454|
|1697770458|8|3|5|277|
|1586466682|5|2|3|379|
|1695134284|0|0|0|238|
|1695128938|2|1|1|533|
|1589998415|7|4|3|196|

Balances equal complete movement totals for six products; source locations are the
exact active __SORTING__, no container. No unlinked FBS movement or unattributed
negative in the original narrow checks. History query also attributes3/17 movements
to two other supplies on these six products; their expense is NOT added to this draft.
No physical location examination or physical shipment/print/sign claimed.

Position reserved_quantity sums14; legacy reservation table sum0, product-reservation
table sum0. These are separate stored channels; equality is not assumed. Supply
remains draft. Local statuses14 done/12 in_delivery/5 cancelled. Native locked
recheck must use actual current reserve semantics, not old reserve16→1 expectations.

Already26 operation facts and52 charges (26 fbs_order/26 packing), no duplicate
order/service or reversal entries. Old11 fact IDs and old22 charge IDs/quantities
preserved;15 facts/30 charges now exist beyond old snapshot. Every positive position
already has one fact/two charges, including remaining14 stock expenses: do not add
new duplicate billing. All52 amounts remain null; monetary settlement unknown.
Existing observed checkpoint is confirmed but not proof all stock expense completed.

Read immutable current observed_handoff_service ozon_targets,completed_quantities,
save_observations/conduct_supply/native locks; never invoked a write function.
Before any integrator action: native locks/recheck exact31/current scope/proof,
ledger/recipe/movement/reversal/reserves/billing; recompute remaining missing again.
These accounting/API reads are separate snapshots and cannot authorize blind14 or26.
Normal publish consequences belong to later native conduct; no publish/sync/observations/
conduct/flags/roles/keys/client message/external mutation executed by collector.

All sanitized raw SELECT CSV/SQL,31 posting projections/scope snapshots, manifests,
reader stdout/exits and producer/copy receipts preserved in this directory. File
manifest hashes every saved member. Only docs evidence committed/pushed; common,
607 writers,product/config/source/protected fixtures and production app unchanged.
This is fresh evidence for integrator, not operational acceptance or a recovery claim.

# WMS-675 · fresh operational preflight, read-only

**Run:** 2026-10-07 06:05:40.794956–06:05:46.725177 UTC. This is a
pre-deploy preparation snapshot, not an apply or VERIFIED deploy proof.
Production `/opt/wms` was still `8f11d912351e8de7633b4abcf74d195badaeb254`.

## Scope and method

The bounded reader verified the exact requested tenant, seller, WMS-source
supply, warehouse and 31 unique order/position rows in a PostgreSQL
`REPEATABLE READ, READ ONLY` transaction and rolled it back before network
I/O. It obtained seller-bound credentials only inside the existing application
account service and did not emit them. It then made exactly 31 semantic reads
of Ozon `POST /v3/posting/fbs/get`, through the configured application
transport; no sync, observation persistence, conduct, SQL write, Ozon
ship/approve/deliver/create, retry or configuration change was made.

Every card matched its scoped position by posting, SKU, offer and quantity=1;
all related/weight posting lists were empty. The sanitized per-posting receipt
is [external-receipt-sanitized.json](external-receipt-sanitized.json), whose
reader receipt hash is `a5543a754b18baaf6ed5295543c07ea92a85fcf0ac0c490d63658b4bfa4a6795`.
The exact accounting receipt, including current fact/charge ID sets, is
[accounting-receipt-sanitized.json](accounting-receipt-sanitized.json).
File SHA-256: external `8f6687c0d02ac1f38b3c55e1839a530ff9023a441877868dc88da37500d282b0`,
accounting `1924f6cbce5eecd2d7080f2e7d44ff6baebb9f4d9c5842c9bc6edf0a81ee5560`.

## Current result

- External proof: 26 positive (12 `delivering`, 14 `delivered`) and 5
  `cancelled`; unknown/composition mismatch/read error: 0.
- WMS scope: 31 orders/positions, statuses 14 `done`, 12 `in_delivery`, 5
  `cancelled`; supply is still WMS/Ozon `draft`.
- Ledger: 31 recipes; shipment/writeoff conducted 0, reversal 0. Therefore
  `already_conducted=0` and **current remaining delta = 26 − 0 = 26**.
- Reserve is now 12. Facts/charges are now 14/28, with no `observed_handoff`
  journal; the recorded supply operations remain confirmed `supply_from_orders`
  and failed `supply_deliver` (`ozon_order_not_assembled`).

The facts/charges/reserve changed since proof `937adf` (13/26 and reserve13)
while ledger conducted remains zero. The historical 11 fact IDs and 22 charge
IDs are still subsets of the fresh lists; the previous 13 fact IDs and 26
charge IDs are also preserved. Fresh list fingerprints are facts
`da4b4ba0ad992568dba0de10987dd1ff24f69094889fed2718144d04a8bc8198` and
charges `c104aa9df459cb230a0c51de1e99757aa1beefc6bd4921abd2b794042e87517a`.

## Consequence after VERIFIED deploy

There is no double-write evidence, but the old 13/26 baseline must not be
reused as a target. After root verifies the actually deployed common SHA, use
the accepted exact-scope path in
[OPERATIONAL_REPAIR_RUNBOOK_20261007.md](../OPERATIONAL_REPAIR_RUNBOOK_20261007.md):
new exact31 proof, full journal/facts/charges-lines check, durable observations,
existing locks and `conduct_supply` with cumulative targets, followed by an
independent readback. It must account for current 14/28/12 rather than invent
an additional 13 facts/26 charges. No production mutation was performed here.

**READY_FOR_VERIFIED_DEPLOY. ACTUAL_REPAIR=NOT_PERFORMED.**

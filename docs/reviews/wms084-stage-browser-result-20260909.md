# WMS-084 / WMS-395: stage Chrome verification, 9 September 2026

Final status: **PASS for actual UI cancellation and reuse of the same physical pool code**,
on staging `50c9c88e0e56097e857fa26e0bda419d69125f9f`. Runtime SHA was checked by the
continuation before any browser mutation. This is stage evidence, not a production claim.

## Successful continuation after the WMS-395 patch

The existing supply and orders were reused without setup. Chrome showed the inline cross
beside the code on A. It was clicked, the real "Отменить КИЗ?" dialog was confirmed, and
the resulting application DELETE returned204. The page then showed "КИЗ отменён" and no
code on A. Scoped SQL showed zero bindings, the same applied physical code and a null
packaging-task-line association. Its source and physical timestamps remained unchanged.
The code did not enter the public available-label list.

The existing ordinary sticker of B was then entered through the scanner, followed by the
same physical KIZ. The live commit returned status ok. The final screen shows A without
the KIZ and B with its tail and inline cancellation cross. SQL confirms exactly one new
binding `ac260815-c7bf-41d1-a168-1ee70fd1b114` on B
`88eaff48-cd04-4a9c-93fc-c6957694099d` / WB500044, referencing the original
MarkingCode `1be09c79-4fd1-465e-9688-a77183af289f`. That code remains applied and absent
from the available-label list. There was no manual status reset.

Complete balance rows, movement IDs and reservation rows were compared with the original
snapshot taken immediately before the first KIZ scan. They matched before cancellation,
after cancellation and after binding B. The two reservations introduced during the earlier
order preparation remain separate from these KIZ actions.

The final marketplace metadata still has status unknown/check_status error, as it did
before continuation. The actual screen says WB has not confirmed the code. **This check
proves local detach/rebind and inventory conservation; it does not claim WB acceptance.**

Evidence is in `wms084-stage-browser-20260909/continuation.json` and screenshots02–06.
Screenshots02,04,05 were opened and visually inspected. Screenshot03 caught the confirmation
dialog during its fade-in and is not used as a legible visual record. For a clear dialog
record, screenshot06 opens the same inline dialog on final B and then clicks **Не отменять**;
it does not detach B. Every owned Chrome instance was closed in finally. The final named
supply and the single binding on B are intentionally retained.

The continuation must not be rerun now: its initial assertion requires the former binding
on A and will correctly reject the final state. No additional orders, picking, shipment,
physical label printing, mocked HTTP or direct API cancellation was performed.

## Initial blocker record (superseded by the successful continuation above)

Initial status: **BLOCKED at the inline cancel button; cancellation/rebinding not yet exercised**.
Application deployment authorized by root: staging `27400e5ff45d4e93eb6afc174f60710f3930abb4`.
This checkpoint contains QA scripts/evidence only, no application changes.

## Actual fixture and preparation

Tenant WMS Staging `9c31f3f4-ce62-4c1f-891a-295b278f1e69`, seller Эмулятор WB
`50110328-fa03-4604-b2e4-8ca27fc8bb41`. Scoped read-only SQL verified the product
`3d6050c5-0d29-4612-9e30-e90ecbf9408a`, SKU `EMU-CAN-PVZ-TRUE`, Куртка демо ПВЗ.
The UI displays the marketplace article `PIDZHAK-VIDEO-05`; this is not a different product.

Old unused orders WB500033/500035 could not form a supply: public preflight returned
`deadline_passed`, deadline 6 September. The attempted create returned409; neither old
order was assigned or scanned. `expired-fixture-attempt.json` preserves the inventory
snapshot taken before all fresh-order preparation.

Root authorized two fresh simulated purchases via the existing emulator admin orders API.
Preflight verified configured admin API, seller_a, warehouse501001, chrt111005,
one suitable template without a fixed createdAt, and published stock51.
The bounded POST created **WB500043/500044** at `2026-09-09T01:37:27Z`.
The prior42 orders have the identical digest before/after; the selected emulator stock
changed51→49 through the normal purchase operation. No reset, old-order edits or metadata
restoration was performed. The helper never writes token values to output.

One public WMS import for this seller completed: job `d6d3ed4e-6b65-4d16-b427-32426bf1c469`.
Both fresh orders have deadline `2026-09-14T01:37:27Z`; public supply preflight was compatible.

| Object | ID |
|---|---|
| A / WB500043 | `24744eed-ab3e-4625-95ef-68c994adad44` |
| B / WB500044 | `88eaff48-cd04-4a9c-93fc-c6957694099d` |
| Named supply | `aa3e89c6-68b9-4fd0-a849-2f8fdec0a988` |
| Supply name | WMS-084 QA 2026-09-09 · 500043 → 500044 |
| Existing physical code | `1be09c79-4fd1-465e-9688-a77183af289f` |
| Code pool | `80a718dd-2487-4951-a1dd-9e13aee562e6` |
| Binding on A | `b0335179-a151-4420-b938-f7a0c4317d1f` |

## Browser facts and blocker

Chrome opened the actual stage supply, clicked Start work and the Packaging/marking tab.
The generated ordinary WB sticker images were rendered and visually inspected.
The ordinary sticker of A was entered through the scanner field, then the existing synthetic
pool KIZ. The live commit endpoint returned success (`status=ok`). No requests were mocked.

The expected inline cancel cross did not appear. A new Chrome session reread the actual row:
the KIZ tail was visible, the row said WB had not confirmed it, and the inline cancel locator
count was **zero**. `01-bound-a-no-inline.png` was opened and visually inspected.
All owned Chrome processes closed through finally blocks.

Scoped SQL after that scan confirms the same code is applied, source pool, with exactly
one binding to A. Binding source is pool, meta_status unknown, check_status error.
The workspace API also returns source pool/status unknown. This report does not claim WB
acceptance. The public available-code list excludes this code.

The current UI's `hasOperatorKiz` requires source operator, and the inline button uses that
predicate. The scan service deliberately saves source pool when the scanned code was
claimed from an available pool. Thus the manually scanned pool code is reachable in this
state but has no inline cancellation control. Root confirmed the WMS-395 requirement does
not restrict the cross to operator-source codes and assigned a separate narrow UI fix.

## Stock evidence and continuation

Before preparation, physical product balances were20+40 and a zero sorting balance;
there were6 movement IDs and9 reservation rows. After fresh import/setup, all balance
rows and movement IDs remained identical; reservation rows became11 due to the two new
orders. That preparation effect is separate from KIZ processing.

The `before_kiz` snapshot was taken immediately before scanning. After the accepted A scan,
balances, movement IDs and complete reservation rows are exactly equal to that baseline.
Raw KIZ values are omitted from every saved JSON file.

**Leave the current objects unchanged until the WMS-395 patch is deployed.** Do not rerun
the setup script against this supply: its initial unused-order assertions intentionally stop it.
Do not call DELETE through the API to bypass the missing button, do not create more orders,
and do not reset the code to available. Resume with the existing supply and baseline:
click A's inline cross, confirm in the actual dialog, verify no binding and code not available,
then scan B's ordinary sticker and the same physical code. Verify the same MarkingCode ID,
a new binding row on B, and unchanged warehouse balances/movements/reservations.

Local ENOSPC interrupted one screenshot and a later evidence write; those attempts were not
counted as proof. After root freed browser caches, the final UI screenshot and scoped SQL
evidence were saved successfully. No browser/profile credentials or application caches were
altered by this agent. Only script syntax checks were run; no full tests/build were repeated.

## Prepared continuation while PR206 awaits stage deployment

`scripts/wms084-stage-browser-continue.cjs` now implements the continuation against these
existing objects only. Its default read-only preflight was run successfully: the runtime
is still `27400e5ff45d4e93eb6afc174f60710f3930abb4`, the original binding remains on A,
the physical code is applied and absent from available labels, and all inventory/reservation
rows still match the original `before_kiz` snapshot. No Chrome or mutation was started by
that preflight. The mutation mode also explicitly rejects this old deployment SHA.

After root verifies and authorizes the new staging SHA, run:

```sh
node docs/reviews/scripts/wms084-stage-browser-continue.cjs --execute-after-deployment-ready=<new verified full staging SHA>
```

The continuation creates no orders/supply, issues no API DELETE itself, and uses the existing
A cross and confirmation dialog before scanning B. It writes a separate `continuation.json`
and screenshots so the initial blocker evidence remains intact. Any failure after a mutation
requires rereading the saved state before further action; do not blindly rerun the command.

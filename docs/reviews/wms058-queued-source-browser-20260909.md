# WMS-058: real stage RED for a queued source scan during over-plan confirmation

**RED confirmed** on staging `50c9c88e0e56097e857fa26e0bda419d69125f9f`.
The run used the actual Chrome UI, actual stage API and actual warehouse balances.
No application code was edited. GREEN requires a separately verified new deployment.

## Scope and owned object

Tenant `9c31f3f4-ce62-4c1f-891a-295b278f1e69`, QA seller
`50110328-fa03-4604-b2e4-8ca27fc8bb41`, warehouse
`307c0ccd-9a6b-41df-9180-f8ed68022237`. Read-only SQL verified product
`45587c50-451f-4d0a-b233-98c07be4dc9d`, SKU EMU-KIZ-OPTIONAL belongs to that seller.
The ordinary product barcode was `2000000000013`.

- A: box **FBSVID-BOX-03**, `817b4384-17ba-4872-9a81-d8f62adc3dfe`, initial35 units.
- B: cargo place **FBSVID-CARGO-01**, `7b100aa1-54c8-4efc-bd61-2bf1e1453374`, initial20 units.
- Both sources were in location `43a2a23a-0653-49de-82f5-b60f2ba48530` on the QA warehouse.
  Current pick-options confirmed availability35 for A and18 for B.

Own document: **№000041 / ОТГР-26-09-09-6**, ID
`9f6f9e7b-8e41-489b-96f1-04d453864f85`, labelled in evidence **WMS058 queue-source RED**.
The public MP create/update contract has no user-editable name field, so the generated
number and this exact ID identify the owned QA object. Plan: one unit of one product.
The new packing box was `WHB-5M7CCS4HQP4GGA`.
The existing WMS084 supply and its final binding on WB500044 were not touched.

## Actual operation and evidence

1. Chrome opened the owned MP packing dialog, scanned A and the product. This fulfilled
   the plan: one picked and boxed unit, A35→34, B20 unchanged.
2. The next product scan sent `allow_over_plan=false`, `container_kind=box`, `container_id=A`.
   The server genuinely returned422 with `{"detail":"plan_limit_exceeded"}`.
3. The browser route used `route.fetch()` and held that real response until B was entered
   into the scanner queue. It then fulfilled the exact response status and body unchanged.
   This was a controlled delivery delay, not replacement data or a fabricated422.
4. After422 delivery, queued B ran while the confirmation dialog was open. The active-source
   chip behind the dialog changed to FBSVID-CARGO-01. SQL showed no stock effect yet.
5. The actual **Добавить всё** button was clicked. Its retry kept the product barcode but
   sent `allow_over_plan=true`, `container_kind=cargo_place`, **container_id=B**.
   The server returned200 and removed one unit from B; A remained unchanged.

Request bodies and their sequence, without headers/tokens, are in
`wms058-queued-source-20260909/red.json`. Both PNG screenshots were opened and visually
inspected: the first shows the modal with sourceB behind it; the second shows two boxed
units after confirmation. Scoped SQL captures exact balance rows and movement IDs.

| Read point | A | B | Loose sorting | Movement rows |
|---|---:|---:|---:|---:|
| Before creating own MP | 35 | 20 | 7 | 19 |
| Plan fulfilled from A | 34 | 20 | 7 | 20 |
| Modal open, queued B selected | 34 | 20 | 7 | 20 |
| Over-plan confirmation | 34 | 19 | 7 | 21 |
| After ordinary MP cancellation | 34 | 19 | 9 | 22 |

The modal-state balances and movement IDs were exactly equal to the plan-fulfilled
baseline. The confirmation introduced the B decrement, proving the wrong source is a
real warehouse effect, not only a changed chip or request field.

## Cleanup and remaining verification

The owned MP was cancelled through its existing public cancel operation, and a GET
confirmed status `cancelled`. Its two units returned to sorting as specified by the
existing cancellation contract. Total physical quantity remained62. Container quantities
were not manually restored. Chrome closed in finally. No external WB operations, shipment,
physical printing, dependency installs or full test suites were used.

RED is complete; further mutations stopped pending root's GREEN deployment SHA.
The same cancelled document must not be reopened for mutation. GREEN should use one
fresh owned MP with the same bounded source/product setup, verify queuedB does not run
before the decision, confirm the immutable originalA request, and then verify queuedB
continues. An additional queued product can check that the next over-plan confirmation
does not overwrite the first pending operation; it was not executed in this RED run.

Reproduction script: `scripts/wms058-queued-source-browser.cjs`. Its default performs
only the live scoped preflight. The explicitly authorized RED mode was run once:

```sh
node docs/reviews/scripts/wms058-queued-source-browser.cjs --execute-red-approved
```

Do not rerun RED: it deliberately exercises the defect and consumes container stock
before returning it to sorting. The report records an observed defect, not acceptance
of this deployed version.

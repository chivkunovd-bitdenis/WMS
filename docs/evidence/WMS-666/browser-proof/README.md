# WMS-666 actual browser and PostgreSQL proof

This directory is reserved for process-level evidence on the exact final release candidate P. It contains a copy of the prior compatibility browser driver with only isolated endpoints and product-SHA recording changed, plus a separately guarded local API server. Product source and frozen expectations are not edited here.

## Isolation

The browser runner uses one dedicated headless Chrome on CDP port 16707, Vite on 16706, an ASGI test server on 16709, a synthetic print endpoint on 17845, and PostgreSQL database `wms_test_666_browser_proof`. The test server refuses any other database name and denies outbound HTTP, so WB and Ozon traffic cannot reach a live marketplace. Never point its reset endpoint at `wms_native_print_*`, another test database, or a service database. The print callback only records the browser payload and returns a synthetic receipt; it is not physical-paper or native-printer proof.

The integration/native proof ports 16692, 16696, 16697, 17843 and its DB are outside this harness and must not be reused. The browser run must also be coordinated so only one Chrome/CDP session is active at a time.

## Candidate and setup

Use the exact final P SHA announced by the release integrator. Before starting, verify the clean source checkout reports that SHA and that each isolated endpoint is free. Reuse the existing frontend `node_modules` and backend virtual environment; do not install dependencies or run Docker.

Create the database only if it does not already exist:

```sh
createdb -h 127.0.0.1 wms_test_666_browser_proof
```

Start the local synthetic API server from the repository root:

```sh
WMS_TEST_DATABASE_URL=postgresql+psycopg_async://deniscivkunov@127.0.0.1:5432/wms_test_666_browser_proof \
PYTHONPATH=backend/tests:backend \
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python \
docs/evidence/WMS-666/browser-proof/audit_server.py
```

Start Vite separately:

```sh
node frontend/node_modules/vite/bin/vite.js --config frontend/tests-e2e/wms652-critical/vite.config.ts --host 127.0.0.1 --port 16706
```

Run the existing actual-API/PostgreSQL React cases from the copied driver (the `supply_id` and `supply_ids` runs each reset only the guarded database):

```sh
WMS666_PRODUCT_SHA=<exact-P-SHA> WMS652_EVIDENCE=docs/evidence/WMS-666/browser-proof/results/supply-id \
WMS666_ENTRIES=supply_id \
WMS666_VARIANTS='normal,delete-before-claim,delete-after-claim,replace-before-claim,replace-after-claim,manual-then-delete-scan,rapid-scans,flags-after-claim,clear-partial,controls' \
node docs/evidence/WMS-666/browser-proof/compatibility-browser.proof.mjs

WMS666_PRODUCT_SHA=<exact-P-SHA> WMS652_EVIDENCE=docs/evidence/WMS-666/browser-proof/results/supply-ids \
WMS666_ENTRIES=supply_ids \
WMS666_VARIANTS='normal,delete-before-claim,delete-after-claim,replace-before-claim,replace-after-claim,manual-then-delete-scan,rapid-scans,flags-after-claim,multi-seller,controls' \
node docs/evidence/WMS-666/browser-proof/compatibility-browser.proof.mjs
```

Run the actual Ozon selected-posting scope separately. This is the twenty-first
case from the expanded audit, not a replacement for either WB entry point:

```sh
WMS666_PRODUCT_SHA=<exact-P-SHA> WMS652_EVIDENCE=docs/evidence/WMS-666/browser-proof/results/ozon-scope \
WMS666_ENTRIES=supply_id WMS666_VARIANTS=ozon-scope \
node docs/evidence/WMS-666/browser-proof/compatibility-browser.proof.mjs
```

Then run the new M41 multi-supply manual coordinator scenarios against the
group entry point. Each case resets only the dedicated proof database. The
partial case includes a single synthetic 503 for supply B; the runner checks
that an explicit retry reaches B alone while supply A stays committed. Cancel
and reload verify that A is not replayed and that the remaining supply is still
available after recovery.

```sh
WMS666_PRODUCT_SHA=<exact-P-SHA> WMS652_EVIDENCE=docs/evidence/WMS-666/browser-proof/results/m41 \
WMS666_ENTRIES=supply_ids WMS666_VARIANTS='unified-partial-retry,unified-cancel,unified-reload' \
node docs/evidence/WMS-666/browser-proof/compatibility-browser.proof.mjs
```

These runs count as PASS only when the actual React action, exact API request,
database state at dispatch, and independently decoded manual HTML payload all
agree. A synthetic response or a rendered label on its own is not sufficient.

## Whole-process extension

The whole-process continuity run is separate from the frozen 21-case matrix:
it starts with a bare supply that has no packaging task, checks real local QR
asset preparation, binds a KIZ through the manual path, captures the dispatched
HTML and acknowledgements, and then exercises WB accepted/rejected readback,
unbind/current reprint, packing, navigation, and boxes. WB outcomes are local
synthetic fixtures; the test server blocks external HTTP. The harness must
record printed and packed counters separately and compare inventory balances,
reservations, and movement count before/after. This is not live-WB or physical
paper evidence.

Status: matrix and M41 commands are prepared but have not been run on a frozen
final P. The whole-process extension still needs its scenario implementation
and an exact P before runtime validation.

## Required evidence per case

Record P SHA, browser/runner SHA, seeded database identities, action sequence, actual request bodies/responses, PostgreSQL state immediately before dispatch and after completion, emulator receipt, and any warning/error. For label output, retain the exact image/HTML delivered to the synthetic print boundary and independently decode the QR/DataMatrix payload. Record `printed` and `packed` counters separately. Do not infer WB acceptance, physical paper, live printer compatibility, or deployment from a synthetic receipt.

Current status: harness prepared; no cases have been run on final P yet.

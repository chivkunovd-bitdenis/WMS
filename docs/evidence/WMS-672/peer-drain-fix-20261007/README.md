# WMS-672 active cohort drain, after separate frozen regression

Previous16-window source9e757a02cefa0cd1f7a95d272944e0b7c2b0660a still failed
actual Linux C5 on corrected299 retry; that failed evidence is85de599e0. Its
message correction worked. This next change addresses reproduced premature
source teardown while other readiness workers remain active; no engine-cause
or Linux-success claim is made before the counterfactual.

Separate testwriter froze a0e4409300d4897234c501474de2bfe45478e488 BEFORE new
product code, cherry-picked97fc3ff72. Developer repeated2 meaningful premature
frame-teardown FAIL. Product changes only printBarcodeLabel.ts handoff cohort:
async wrapper captures synchronous decode throws, original Promise.all retains
first failure, and its catch awaits allSettled of already-started peers before
rethrowing the SAME error. Existing outer cleanup then removes iframe. No further
cohort starts after failure; no print/source save/mark occurs. Successful allN
native readiness/one print and non-handoff scan path stay unchanged. Window16,
yield/fallback/assertion timeouts, source generation and screen are unchanged.

After change: frozen2PASS; previous frozen7PASS. Async case includes a later
failure in a lower-input-index peer: first error identity/reason is retained.
Sync case captures peers started before direct throw. Both record source alive,
operation unfinished/busy/attempt active while peers held, then cleanup at0pending.
Old7 retain invalid-asset abort and held all300 readiness/one transfer/300marks.
All old11/C5/native7/config and new2 test sources hash-equal their frozen commits.

Commands from repository root:
```
node --test --test-reporter=tap frontend/tests-e2e/wms672-peer-drain.test.mjs
node --test --test-reporter=tap frontend/tests-e2e/wms672-native-errors.test.mjs
cd frontend
npx tsc --noEmit -p tsconfig.app.json
npm run build
```
Both typecheck/build exit0; normal bundle-size warning only. Existing shared
dependencies used; no install/local browser/printer. Before/after rawTAP and
receipts saved here. Actual Linux141 comparison2+7+unchangedC5 and native
pending/fulfillment/removal observations are next, sole dispatcher integrator.
No policy/reference self-approval, CI/product-outside-owned-path edit, real print,
production/operator action or fullCI execution here.

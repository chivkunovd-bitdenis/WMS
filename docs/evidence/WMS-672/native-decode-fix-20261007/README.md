# WMS-672 narrow native decode correction

Authorized baseecb1d5721ea823a0ffd861303302c4b8dc731e6d. Separate testwriter froze
05a7d08a65e135256fa69e8bf84519e95bcdef96 BEFORE product code; unchanged contract
cherry-picked as a52257b23. Developer repeated actual source RED3/4PASS, then
changed exactly two product paths. No old/new test expectations/config modified.

- `printBarcodeLabel.ts`: handoff native decode window32→16; parallel Promise.all,
  parent-frame yielding/fallback and strict all-image-success before print remain.
  Non-handoff scan print path is unchanged. No native-failure bypass/retry loop.
- `FfInboundRequestView.tsx`: retain nonempty string message from an error object
  across iframe realms. Empty/malformed message uses the existing generic alert.
  Failed preparation still removes iframe, clears busy and does not save success,
  print, or mark labels.

Local commands and results (shared existing frontend dependency symlink; no npm
install, no Mac browser/printer):

```
node --test --test-reporter=tap frontend/tests-e2e/wms672-native-errors.test.mjs
# Before code:3 message assertion FAIL,4PASS,0skip; after code:7PASS,0skip.
cd frontend
npx tsc --noEmit -p tsconfig.app.json
npm run build
# Both exit0; normal bundle-size warning only.
```

Exact before/after TAP, typecheck/build logs and frozen-source hash receipt are
saved alongside this file. The seven boundary tests cover native iframe message,
invalid asset abort, malformed fallback, held parallel preparation and readiness
of all300 before one source save/transfer and300 marks. jsdom platform mocks do
not prove actual Linux image decoding. The32→16 resource-pressure proposal still
requires one coordinated unchanged C5 comparison on Linux/Chrome141; no internal
engine-cause claim is made and no timeout changed. Full11 remain frozen, not
rerun locally; fullCI follows independent review on integrated candidate.

No product/reference policy self-approval, UI redesign, generator change, CI edit,
real printer, production/operator action, fullCI or Linux dispatch by developer.

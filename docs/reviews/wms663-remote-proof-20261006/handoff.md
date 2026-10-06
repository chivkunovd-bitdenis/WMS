# WMS-663: C16 selector correction and bounded remote evidence

Separate tester, 06.10.2026, following analyst commit
923961749907ee212d450f25b19950c43b270ce0 and its complete current acceptance report.
Fresh origin/etalon 954862b718f9f2f1faefb2f00ad2fef72a6e1929 AGENTS.md read fully.
Requirements R1–R15/C1–C19, previous correction handoffs and protocol read.
No skills, other agents, Mac browser, Playwright, local PostgreSQL, npm ci,
credentials management, live writes, Telegram, external signature/stock/print,
merge or deployment used. Untracked WMS-675 and CLI result files belong to others.

## Exact fixture delta for independent Astra high review

Published correction commit: d9e022697e098a2f9c0feee6a5bf03f99cac5945,
parent: 923961749907ee212d450f25b19950c43b270ce0.
Only one tracked file/line changed:
`frontend/src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx`.
Before blob: 8548a75eb6963edcd5e3b3755e0a618d918f9f94.
After blob: 7b41916c4 (full Git object available via correction SHA).

```diff
-    const close = button('Закрыть')
+    const close = document.querySelector<HTMLButtonElement>('button[aria-label="Закрыть"]')
```

Real workspace IconButton already has aria-label="Закрыть" and CloseIcon.
Its textContent cannot match the old helper. This selects the existing accessible
button; no new product control, disabled filter, test expectation, timing, payload,
assertion, skip or case changes. All 16 expect expressions remain byte-identical.
The correction commit contains only the frozen test, no report or product code.
Independent review of this exact delta is pending; no PASS added to the correction
registry, checker or guard transform. Product 1fd2d92 and its unchanged e27 PASS,
protocol 86b and unchanged 749 PASS are not repeated or reinterpreted.

## C16 local bounded result

Exactly one invocation of the existing Vitest binary, one worker, 150-second
process-group limit. Command from frontend:
`./node_modules/.bin/vitest run src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx --maxWorkers 1 --minWorkers 1`.
Result: 1 test/1 file PASS, exit 0, elapsed 107.86s; Vitest 107.32s,
collection 105.87s, test 853ms. Raw output: c16-local.txt.
No retry. Frozen scenario is GREEN; its final navigation assertion only focuses
Close, so this alone does not close the entire C16 refresh/B/tab requirement.

## Remote runner scope

New narrow workflow `.github/workflows/wms663-remote-proof.yml` reuses checkout,
Python/Node installation, isolated postgres:16 service and artifact upload from
existing CI. Runner Chromium/CDP pattern reuses WMS666 remote proof
(ec4313f584a96a9c9fd485101e7d29c381fcc113); no Playwright or new test framework.
Triggers only this branch and the owned helper/workflow paths. This is targeted
proof, not full CI, acceptance or a release. It never deploys or reads secrets.

C10 runs the unchanged frozen two-session test, explicitly rejects SKIP, plus an
addressed mixed doc/mark writer helper. An Event holds the first document claim
while a separate PostgreSQL session attempts marking. Conflict must prevent a
second pending SET. After a matching synthetic acceptance, explicit marking
continuation must preserve GTD, existing marks and other SKU and use a new version.
All external calls use FakeMarketplaceTransport and generated fake identities.

C18 builds the unchanged real FfFbsSupplyWorkspace and actual theme from the exact
product source, using existing frozen fixture builders read-only. Synthetic
fixture has exactly two SKU and three total units (2+1), long product name and
60+ character numbers with leading zeros/separators. Runner Chrome renders 1280
and 390 px; screenshots, DOM, accessibility tree, field/checkbox geometry, browser
version and source manifest are artifacts. No illustrative HTML replaces product
UI. Fetch is synthetic, other browser network blocked, print/window.open forbidden.
This proves a synthetic compiled UI, not a deployed backend or Sonnet mockup.

Additional original C16 steps only: rejected→correction→save→GET refresh→keyboard
tab→remount/readback. C10 duplicate UI click must emit one synthetic PUT.
Order B is not claimed covered. No new business checks beyond original C10/C16/C18.
Runner outcomes and URLs will be recorded after completion; no PASS assumed.

## C17 and C19 remain open

06.10.2026 public primary source only: official Ozon Seller API set/status anchors
both return `400 Redirect loop detected` through web. No mirrors, credentials or
Seller API calls. G2 fresh official contract remains unverified; existing saved
OpenAPI is unchanged. URLs:
https://docs.ozon.ru/api/seller/#operation/PostingAPI_FbsPostingProductExemplarSetV6
https://docs.ozon.ru/api/seller/#operation/PostingAPI_FbsPostingProductExemplarStatusV5

C19 external cycle NOT AUTHORIZED, NOT EXECUTED, NOT PASS. The unchanged analyst
must resolve its relation to the original request; this tester changes no R/C,
acceptance verdict or conclusion. New fixture delta needs its own independent
Astra high review and supported protocol registration by the owning reviewer/
controller; previous unchanged reviews or acceptance are not rerun.

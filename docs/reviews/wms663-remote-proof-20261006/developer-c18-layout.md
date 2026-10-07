# WMS-663: developer handoff for the confirmed C18 narrow layout defect

06.10.2026. Scope assigned directly by owner: Sol 6.1 developer only; product
layout plus this handoff. No delegated agents or review claim. Fresh origin/etalon
rules, local AGENTS.md, requirements R1–R15/C1–C19, tester handoff and developer
skill read. Existing checkout/branch retained to preserve the published proof and
other contributors' work. Developer starting product parent:
08895fa93e38a7e85d75aad455a8741194a32897 (analyst evidence commit arrived during
read-only inspection, before the layout edit).

## Published RED before implementation

Separate tester proof:
- 01dec4491cfb221e0d1b061e4908d45c01b05989, run 37439193822.
- b244578d896cb2a694a900229f9da271d40d1667, run 37439508519.

Both preserve C18 1280 PASS / 390 FAIL. Existing local actual Chromium screenshots
`remote-ui-b244/c18-390-documents.png` and `c18-1280-documents.png` inspected using
view_image, no Mac browser. Published 390 geometry has document block width=0,
all three TextField container widths=0 / input widths=28 and checkbox label
clipping. Screenshot confirms character-by-character text. No weaker replacement
criterion or new test added.

## Baseline and minimal change

Existing baseline `7d9e9a63c^:frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`
already has the horizontal packing row, flexible product column with minWidth=0,
and nonshrinking sticker/marking columns. WMS-663's document component was placed
inside that column. The parent exhaustion predates the new document panel; the
new panel inherits it. The document rows already stack fields and checkboxes at
narrow widths. Fixing that parent allocation avoids duplicate panel layout rules.

Only product file changed: `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`.
Three layout properties in the existing packing order row:
- Ozon uses native flex gap so wrapped children do not retain horizontal Stack
  spacing margins from the prior line.
- Ozon row wraps below the existing theme's md breakpoint (900 px).
- Ozon product/document column takes a full line below md, returning to the
  original flexible allocation above md.

The same DOM, order identity, theme, controls and handlers remain. WB keeps its
original flex/spacing behavior. No document state/request/permissions, scan,
printing, business lock, screen, table or service change. The documents component
itself needed no edit. Other pre-existing narrow header/toolbar geometry is
outside this confirmed defect and has not been redesigned.

## Local verification and limits

`git diff --check`: PASS.
Existing binary only: `cd frontend && ./node_modules/.bin/tsc --noEmit -p tsconfig.app.json`,
150-second bound, one invocation, exit 2 after 14.05 seconds. Diagnostics:
TS2307 missing local pdf-lib in fbsPdfPrintTape.ts, its test and
printMarkingCodeLabel.pagination.test.ts; TS7006 page in fbsPdfPrintTape.test.ts.
No diagnostic in the changed workspace file. This is not a typecheck PASS.
No dependency installation/build: available disk about 528 MiB. No local browser,
live writes, credential management, printing, merge or deployment.

## Exact next evidence required from the owning tester/reviewer

Use the published commit containing this handoff as the candidate product SHA
(and git ls-tree manifest), rerun the SAME real compiled workspace/theme C18
1280/390 probe and unchanged assertions from the published RED. Inspect its
actual document screenshots and geometry; retain two SKU/three units, long name,
60+ character numbers, readable fields/checkbox labels and neighboring actions.
Remote GREEN is pending; local layout reasoning is not visual proof.

The current tester-owned workflow only triggers on helper/workflow paths and its
product identity step requires no frontend product diff from 1fd2d92. Therefore
a product-only push cannot by itself execute a valid candidate proof. The owning
tester must register the new candidate identity/trigger and select C18 while
preserving all expectations. Developer did not edit tests, requirements, runner
or workflow. Previously completed C10/C16 need no unchanged rerun.

Independent Astra high review of this exact product delta is required by the
owner and pending. Review must cover narrow readability, 1280 continuity, Ozon
order context and preservation of WB/scan/print behavior. No additional agents or
historical review loops launched by this developer. This is a published candidate
for targeted proof/review, not acceptance, readiness or deployment.

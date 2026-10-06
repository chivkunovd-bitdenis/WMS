# WMS-663: separate tester C18 postfix evidence

06.10.2026. Direct owner scope: C18 only; no skills or other agents. Fresh
origin/etalon 954862b718f9f2f1faefb2f00ad2fef72a6e1929 rules and local AGENTS,
developer-c18-layout.md, result.md and handoff.md read. Existing named checkout
retained; concurrent C7 backend and registry/checker changes were not touched.

## Immutable source and exact remote execution

Product source: aa57886772d746d0a08341867d8828bf3ed84d5a.
Published runner commit: b84d43cb4b7f22f5b791603062dbc95a13dc9b60.
Run: https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37440603288
Run conclusion success; UI job success; C10 PostgreSQL job skipped by explicit
opt-in. proofScope=c18 and result cases contain only C18 1280 and C18 390.
No C16 execution or synthetic PUT; requests.json contains only two synthetic GETs.

Workflow restores the entire frontend from the immutable product commit before
install/build, retaining probe helpers from the runner commit. Source SHA and
git ls-tree manifest are saved. Frozen fixture blob at product source and d9e022
is identical: 7b41916c43bf144d9fdeb7772d415bdf5535ff05. prepare-ui.mjs is unchanged.
Only source pin and C18 selection/wrapping changed in workflow/browser helper.
All original geometry/business assertions and 2 SKU / 3 units, long name and
60+ character numbers are unchanged. No product, test, requirements, checker or
registry writes. Node syntax check and owned diff check passed locally.

## C18 result and visual inspection

Chrome/154.0.8037.57 on GitHub Linux, real compiled workspace and application
theme with synthetic fetch: 1280 PASS; 390 PASS; browser errors=[] and forbidden
network absent. Evidence is in remote-ui-b84d/result.json and geometry files.

1280 regression baseline preserved: document block width/height 423/547.453125
and input widths 228.46875, 228.46875, 217.015625 exactly match saved first RED
run's 1280 PASS geometry. Prior 1280 and 390 actual document PNGs were recovered
from b244 artifact 11400996133 and saved in remote-ui-b244; no prior RED JSON or
report overwritten. Original 390 width=0 FAIL remains recorded.

390 now: block width=249, all three inputs/field containers=240. Each row has
no field/checkbox overlap and no checkbox label overflow. Five document controls
have positive bounds; horizontal window overflow=false on both viewports.

Actual new 390/1280 document PNGs opened with view_image. New 1280 screenshot
also compared visually with the recovered baseline PNG. Visible GTD fields and
checkbox labels are readable, do not collapse/clip or overlap; the long name
wraps by words at 390. Long numbers retain their full DOM values while native
single-line inputs show only the visible portion. The narrow screenshot scrolls
the first document fields into view: lower RNPT/control visibility is not all
contained in that single viewport; their geometry is independently saved for
all three rows/five controls. No claim of a full-page visual inspection is made.
The existing narrow header date-save button and partial tab are visibly clipped,
as outside the developer's confirmed document-column defect. No blanket claim
that every workspace element is unclipped; reviewer should retain this boundary.

Retained new evidence: 12 files, 589452 bytes including four actual PNGs, both
geometry JSONs, result/requests, source/probe identity, manifest/browser version.
Chrome version metadata trailing whitespace trimmed; other retained artifact
contents unchanged. No mass install/browser/DOM/accessibility logs copied. GitHub artifact 11400857984
compressed size=567391 bytes. Existing proof and recovered baseline preserved.

## Handoff and remaining gates

Targeted C18 document layout proof is GREEN. This is not WMS-663 acceptance,
independent review, full CI, release or deployment. Separate reviewer must review
the product aa578 delta and tester source/scope delta; analyst must later accept
against current requirements. C10 PG 37439193822 (2 PASS) and C16 37439750397 PASS
were not repeated. C7 and registry process remain owned by their active workers.
C17/G2 and C19 are not changed or newly proved by this run.

No local browser, local npm ci, new framework, external/live calls, secrets,
printing, deploy, merge or full CI initiated. GitHub push and remote Chromium
were the explicitly authorized execution surface. Only owned files are committed;
evidence-only push does not retrigger the proof workflow's path filter.

# WMS-363 — box scan sequence P2 follow-up, 10 September 2026

Execution evidence for WMS-415 coordinator and repeat independent review. This
replaces the rejected mobile candidate in main commit
`125a50eb8ad72ba03c46e6a245c78cb86118f623`; it is not release acceptance.
The owner's latest independent review was read in full before this delta.

## Exact source and delivery

The existing Android path was checked before editing:
`/Users/deniscivkunov/Projects/WMS/.worktrees/wms397-mobile/android`.
The extra `mobile/android` path in the latest instruction does not exist.
Local Android commit: `c9d27e16e992a52ae80b9f7127aad16967f1915d`.
Only these two files changed after `30bab83d94eada0ecc15f877be62fc8aa877ffa8`:

- `android/app/src/main/java/ru/wms/tsd/features/fbs/FbsViewModel.kt`
- `android/app/src/test/java/ru/wms/tsd/features/fbs/FbsViewModelTest.kt`

Main branch `feat/wms363-ozon-tsd` carries only this report and safe artifacts in
`artifacts/wms363-box-sequence-20260910/`. Nested Git history is not pushed.
`mobile-WMS363-box-sequence-delta.patch` contains this two-file correction.
`mobile-WMS363-review.patch` is cumulative relative to
`b77e31a8cc658a23d9c20a318f4f869e304752cc`, as requested. It also carries the
previous accepted streaming changes in FbsApi.kt, FbsPrinting.kt and
FbsApiContractTest.kt, for five files total. Both reverse-apply checks passed
against the final committed Android checkout. These two patches are alternatives;
do not apply both. No backend, migration, App, updater, signing configuration,
coordinator/canon, inventory or chat changes are part of this delta.

## Sequence correction and regression evidence

The four new regression tests were run before changing production code. All four
failed against 30bab83d: WB/Ozon, each starting with A or with no selected box.
They scan BOX-B, suspend its initial refresh, queue a product, then manually select
A before releasing refresh. This reproduces the review's preceding-box case and
checks that the later manual selection is preserved. The assignment simulates a
successful server write with a lost response; retry must reconcile that same B
assignment without a second write. `regression-before.json` records the failed run.

A known box barcode now applies selection synchronously when scan() accepts it,
before the existing queue captures the selected box. Thus the following product
captures B even while BOX-B's refresh is pending. Completion of the box scan only
validates the captured box and never overwrites a later manual selection. If a box
barcode is first discovered by refresh, the operator gets an explicit request to
scan that box again against the refreshed list. No new queue, entity, counter or
navigation gate was added. The product recipient and resolved assignment body
remain fixed across retries. Packaging and stock behavior are unchanged.

## Checks and replacement candidate

74 scoped tests passed: FbsViewModelTest 39, FbsApiContractTest 9,
FbsDeliveryTest 14 and UpdateTest 12. This includes the four new regressions,
existing manual A-to-B after product enqueue, waiting behind a busy operation,
lost-response reconciliation, and streaming oversized/unknown-length tests.
No tests were skipped. lintDebug passed with 0 errors and 41 warnings;
assembleDebug passed. All Gradle invocations used max-workers=2,
ActiveProcessorCount=2, in-process Kotlin and the existing JDK17/SDK/build process.
Only these four test classes ran; no full Android/backend suite was run.
`checks.json` contains the counts from the actual XML results.

Replacement APK: `WMS-TSD-0.1.9-e2685e7772fc-debug.apk`, 45,624,726 bytes.
SHA-256: `e2685e7772fcdcee00a871002b083043d90e2e7490b6f435bf291940c023c98b`.
Package `ru.wms.tsd`; versionCode 10; versionName `0.1.9-ozon-tsd`;
minSdk 24, targetSdk 35, debug. apksigner verification passed. Public certificate
SHA-256: `e343ab0cccc6284b271a72da42a67b14a0f0893d92b9ca461f1cac3d0be1aeb6`,
matching the expected v9 certificate and previous candidate.

The APK is stored locally in the artifact directory and ignored by Git; the safe
patch, checks, metadata and draft update-candidate.json are committed. Its future
release URL is not a published download. Version 10 stays unchanged because the
rejected candidate was never published. No APK or release manifest was published.

## Scoped emulator check of this exact APK

The candidate was installed locally with adb install -r on emulator-5554.
Actual UI taps selected the existing synthetic account, entered its saved fixture
PIN, opened FBS, selected Ozon, opened WMS363-ozon-unfinished and then Короба.
The existing box FBS-21E363E0-001 was opened without changing its contents.
After HOME and bringing the current activity back to the foreground, the same
expanded box and two synthetic order rows were visible. The fresh screenshot
`artifacts/wms363-box-sequence-20260910/resume-box.png` was visually inspected;
this one background/foreground cycle did not show a white screen.

Only the pre-existing isolated fixture API on 127.0.0.1:18083 was used. The app
reached that fixture with its retained server/account configuration after the
local installation; no account storage or credentials were read. No box assignment,
packing, delivery or stock action was tapped. This is a scoped local launch/resume
check, not an emulator reproduction of the delayed-refresh race and not an update
channel or physical-device acceptance. The deterministic four regression tests
provide the delayed-refresh evidence.

## Limits and required acceptance

Repeat independent review must assess this exact source and APK before publication.
Actual app-button update 9-to-10 and subsequent PIN/server/unfinished-document
acceptance require the later authorized release. A local adb install does not
prove that channel. No physical ATOL/scanner/printer or 58x40 output is claimed.
The intermittent white-screen root cause and physical pause/resume remain open.
WMS-402 PC-agent work is not changed or accepted by this correction.

The accepted streamed-download bound remains 16 MiB per input file. Total batch
memory is still not bounded by the per-PDF 32-page guard; the concrete resource
assessment remains in `wms363-p2-followup-20260910.md`. No arbitrary batch/page UX
prohibition was introduced, and prior emulator print observations are not claimed
as new checks of this APK. Protected supply and client warehouse data were not used.
No PROGRESS.md, raw mobile events/logs, signing material or broad nested history
was read. No root/frozen checkout, shared backend or coordinator documents changed.

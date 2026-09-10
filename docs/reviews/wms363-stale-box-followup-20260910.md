# WMS-363 — stale box recovery P2, 10 September 2026

Safe execution report for WMS-415 coordinator and repeat independent review.
This supersedes the Android candidate carried by main commit
`3210e7d12cccc0e3c894590ea3881fc911da04bd`. It does not change the independently
accepted backend in PR213 and does not constitute APK acceptance/publication.
The owner's complete follow-up review of c9d27e16 was read before this fix.

## Exact source and scope

Existing paths were verified before editing. Local Android commit:
`beb2ba6dea046845e93c5c56c73963a7fb0ee117`, in
`/Users/deniscivkunov/Projects/WMS/.worktrees/wms397-mobile/android`.
Only these files changed relative to c9d27e16e992a52ae80b9f7127aad16967f1915d:

- `android/app/src/main/java/ru/wms/tsd/features/fbs/FbsViewModel.kt`
- `android/app/src/test/java/ru/wms/tsd/features/fbs/FbsViewModelTest.kt`

Main branch feat/wms363-ozon-tsd carries only this report and safe artifacts in
`artifacts/wms363-stale-box-20260910/`. Nested Git is committed locally, not pushed.
`mobile-WMS363-stale-box-delta.patch` is the two-file delta from c9d27e16.
`mobile-WMS363-review.patch` is cumulative from
`b77e31a8cc658a23d9c20a318f4f869e304752cc`, additionally retaining the accepted
FbsApi.kt, FbsPrinting.kt and FbsApiContractTest.kt streaming changes. Both patches
passed reverse-apply checks against the committed Android checkout; use the patch
appropriate to the base, not both. Their exact hashes are in candidate-metadata.json.
No backend/shared migration, App, updater, signing configuration, stock, navigation,
coordinator/canon, inventory or chat file was edited.

## Recovery behavior

The existing Channel consumer receives a scan before waiting for busy/error to
clear. Draining only the channel would miss the already-received item when a
failed refresh is retried. A set of pending scan references now covers both
channel items and that waiting item; it is in-memory queue bookkeeping, not a
business entity or persisted journal. Each physical scan retains reference
identity, so identical successive barcodes remain distinct.

If refresh first discovers a box different from the captured recipient, the box
scan is rejected. All still-pending scans in boxes mode for that same supply are
explicitly invalidated, including the already-dequeued waiter. Other modes and
other supplies are excluded. The selected box is cleared to require a fresh
recipient. The error identifies the affected scope and exact pending-scan count:
the current box scan was not applied, the pending scans of this supply's Короба
tab were cancelled, and the operator must scan the box and products again.

Closing the message releases the consumer, which skips those explicitly cancelled
items. Retry acknowledges this rejection without replaying captured stale targets
or cancelling new scans made after the message. A fresh box/product pair scanned
before acknowledging the message therefore survives and goes to B. This special
rejection does not change retries after an actual assignment: those still retain
the same recipient/body and reconcile a lost successful response without another
write. A post-refresh supply check also prevents applying old-supply recovery to
a different open workspace. Known-box immediate selection and later manual choice
remain covered by the preceding regression tests.

## Regression-first and scoped checks

Eight new regression tests ran against unmodified c9d27e16 production code and
all eight failed; the recorded counts are in regression-before.json. The final
tests cover 32 combinations: WB/Ozon, initial A/null, immediate discovery versus
discovery on retry after a transient refresh failure, and close/retry/rescan-close/
rescan-retry recovery. No old product may go to A. Fresh scans after the rejection
can go to B even when queued before the message is acknowledged. The transient
failure cases specifically exercise the already-dequeued waiting product.

A ninth new test checks two identical cancelled product scans, their reported
count, continued execution of a queued pick-mode source scan, and subsequent box
assignment in another supply. Existing known-box fast-queue, manual A-to-B change,
lost-response idempotency, streaming size/unknown-length and updater tests remain.

83 scoped tests passed with zero failures/errors/skips: FbsViewModelTest 48,
FbsApiContractTest 9, FbsDeliveryTest 14, UpdateTest 12. lintDebug passed with
0 errors and 41 warnings; assembleDebug passed. Existing JDK17/SDK/build/signing
process, max-workers=2, ActiveProcessorCount=2, in-process Kotlin. Only these four
test classes ran; no full suite/backend tests or CI rerun was requested.

## Exact unpublished candidate

Local APK: `artifacts/wms363-stale-box-20260910/WMS-TSD-0.1.9-cfe8b5adc1bb-debug.apk`.
Size: 45,624,909 bytes. SHA-256:
`cfe8b5adc1bbd62e728184b9a18a1e5a14a837b3028de865e493c6203bd36870`.
Package ru.wms.tsd, versionCode 10, versionName 0.1.9-ozon-tsd, minSdk 24,
targetSdk 35, debug. apksigner verification passed. Public certificate SHA-256:
`e343ab0cccc6284b271a72da42a67b14a0f0893d92b9ca461f1cac3d0be1aeb6`.
Version 10 remains unpublished; no version/signing configuration change was made.
APK and build logs are ignored by Git. Safe patches, results and candidate metadata
are saved in main Git; update-candidate.json is only a draft future manifest.
No APK or release manifest was published.

## Emulator and handoff boundaries

The interrupted baseline-preparation report was not completed and is not claimed
as acceptance. Its existing untracked files were preserved outside this change.
This fix performed no emulator installation or UI actions. A filtered package
query confirmed emulator-5554 still has versionCode 9,
0.1.8-wms401-orders-first. Desktop/browser focus was not used.

PR213 was queried read-only: state MERGED, mergedAt 2026-09-10T08:08:23Z, head
3210e7d12cccc0e3c894590ea3881fc911da04bd. The main-branch push is allowed only after
that state; PR213's backend acceptance does not accept these Android artifacts.

Coordinator status: WMS-363 candidate awaits repeat independent review. WMS-401/
WMS-412 app-button 9-to-10, PIN/server/unfinished-document acceptance remains for
the later root-authorized publication and actual application download/install.
No adb installation of v10 is permitted as proof of that update channel.
Physical ATOL/scanner/printer and WMS-402 are not checked or changed in this pass;
physical printing is not asserted as a prerequisite for the authorized preview.
The earlier total-batch print-memory limitation remains unchanged.

No client/protected supply data was used or mutated. No PROGRESS.md, raw mobile
events/logcat, stored auth, signing material or broad nested history was read.
No children, reset, root/frozen checkout edits, main merge or deploy were performed.

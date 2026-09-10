# WMS-401 / WMS-412 · local mobile recovery candidate · 2026-09-10

Status: local candidate verified within the bounds below; not released. Root owns the single final review and any later stage/release decision. No production, public APK, update manifest, client stock, protected supply, or printing operations performed.

## Immutable source and APK

Android source: `af9693126d19d16918abd5cc7b7fbe99dfebc142`, local nested commit preserved, never pushed. Narrow six-file delta against accepted `beb2ba6dea046845e93c5c56c73963a7fb0ee117` is [mobile-WMS401-recovery.patch](artifacts/wms401-login-recovery-20260910/mobile-WMS401-recovery.patch). Reverse application against source passed. Main WMS feature branch carries this safe delta, metadata and evidence only.

APK: `docs/reviews/artifacts/wms401-login-recovery-20260910/WMS-TSD-0.1.10-8435c3abcd24-debug.apk` in the permanent wms363-ozon-tsd checkout (binary intentionally not in Git).

- SHA-256: `8435c3abcd240afbaadb95e157512d52a56c105fd73440e6991933741237a81f`
- Size: 45,298,277 bytes.
- Package `ru.wms.tsd`; versionCode **11**, versionName **0.1.10-mobile-recovery**; minSdk24, targetSdk35, debug; arm64-v8a/armeabi-v7a/x86/x86_64.
- `apksigner verify`: valid v2 signature, one signer; certificate SHA-256 `e343ab0cccc6284b271a72da42a67b14a0f0893d92b9ca461f1cac3d0be1aeb6`, matching accepted v10. No signing configuration or key changes.

[Candidate metadata and exact six file hashes](artifacts/wms401-login-recovery-20260910/candidate.json).

## Confirmed defects and fixes

On installed v10, opening password login → server settings → Android Back left the app. Tapping its launcher icon reopened the same password form, with no route to saved staff. Screenshots 01/02 record this before state. `LoginScreen.kt` had no Back handler or return callback from the password form.

The password form now handles Back: close server settings first, then return to saved staff. A text button returns directly to staff. PIN Back also returns to staff. Login completion consumes Back while the request is in flight, and the return button is disabled then; this avoids authenticating a form after it was closed. No PIN, token, server preference, login persistence, or updater logic changed.

The first FBS screen already places all orders before active supplies and uses parsed chronological timestamps. In operation screens the existing unfinished-first sorting compared timestamp strings, which could invert oldest-first order for mixed offsets. `sortedOperationOrders` reuses the existing parsed-time sort, then stably groups unpicked before picked orders. No new mode, status, blocking rule or business entity. Existing deadline/picked colors remain unchanged.

## One final technical run

Ran offline, Gradle max-workers=2, JVM ActiveProcessorCount=2 / heap1200MiB, Kotlin compiler in-process:

`:app:testDebugUnitTest` restricted to `FbsViewModelTest`, `AuthManagerUrlPersistenceTest`, `ServerHealthCheckTest`; then `:app:lintDebug :app:assembleDebug` in the same invocation.

**60 tests passed**: 49 FBS ViewModel, 6 auth URL persistence, 5 server health. Zero failures/errors/skips. Added coverage for WB/Ozon mixed-offset ordering in both picked/unpicked groups and explicit old HTTP:8088 → HTTPS login preserving saved staff and PIN. The latter uses a mocked API response and is not a real TLS handshake.

**BUILD SUCCESSFUL in 5m 50s.** Lint: 0 errors, 41 warnings, 2 information entries. Build once; no full suite or accepted network-update rerun. [Tests](artifacts/wms401-login-recovery-20260910/targeted-tests.json), [build summary](artifacts/wms401-login-recovery-20260910/build-summary.json).

## Actual emulator verification

Owned emulator-5554, Android15/API35; existing isolated fixture at host127.0.0.1:18083 / emulator10.0.2.2:18083. Local `adb install -r` installed v11 over v10 without clearing data. This is candidate installation for local UI checks, not network-update acceptance; accepted 9→10 remains prior evidence.

On v11, actual taps and Android Back verified: settings → password form → saved staff; direct return button from expanded settings; PIN → staff. Force-stop was not used for these repaired transitions. Screenshots 04–07.

Actual server field was changed to `https://10.0.2.2:18083/`. This owned fixture serves HTTP, so pressing connection check correctly showed `Ошибка защищённого соединения [NET-TLS]`. Restoring the working address returned `http://10.0.2.2:18083/` and connection check succeeded. No silent URL migration or persistence of the unsuccessful HTTPS candidate. Screenshots 09/10. Successful HTTPS login on a real trusted TLS endpoint is outside this isolated run; the URL/PIN persistence path is covered by the scoped mock test.

Existing synthetic documents were read through an explicitly read-only SQLite connection: WB `95b8355c-fb2f-4911-a0bd-8fce0021250e`, draft, two orders; Ozon `21e363e0-e6c6-49b6-8e80-92af50b3a982`, assembling, two orders. [Baseline](artifacts/wms401-login-recovery-20260910/synthetic-documents-before.json).

During the pre-candidate v10 cold-start attempt concurrent with Gradle, UI hierarchy reading exited137 and a screenshot showed the Android splash logo. That attempt is inconclusive, not a passed process-recovery check and not proof of an application blank-screen defect. Gradle subsequently completed and its daemon was stopped before candidate UI verification.

## Candidate FBS UI

The same known synthetic PIN authenticated successfully after installation. Actual WB and Ozon screens show orders first, older Sep08 before Sep09, followed by active supplies. The overdue Sep10 order is pink/red; the future Sep11 order uses the normal background. Both screenshots were visually inspected. This demonstrates the current fixture's overdue/future cases; the exact exclusive six-hour boundary is covered by the existing test in the selected FBS class. Original WB supply opens with picked0/packed0; original Ozon picking shows its two positions/orders with picked0. No warehouse action was invoked. Screenshots 11–14.

The installed `/data/app/.../base.apk` public binary was hashed directly (no app data read) and exactly matches the candidate SHA. Filtered package metadata confirms version11. [Installed package evidence](artifacts/wms401-login-recovery-20260910/installed-package.json).

## Background and process recreation

On the Ozon picking screen, pressed HOME and left the app in background for **323.5 seconds**. Tapping the launcher icon returned to the same picking screen and both original orders. PID was unchanged. Screenshot15 and [timed background evidence](artifacts/wms401-login-recovery-20260910/background.json).

Then pressed HOME, verified launcher was foreground, ran `am kill ru.wms.tsd` and confirmed PID absent. Relaunch via the app icon produced the saved staff picker, with a different PID and no blank screen. Screenshot16 and [process evidence](artifacts/wms401-login-recovery-20260910/process-recreation.json). This removes a background process without force-stop, uninstall, clear-storage or auth-data reads.

The same known PIN then restored the saved Ozon picking route automatically, with both original orders visible; no manual document search and no blank screen. Back opened `WMS363-ozon-unfinished`, picked0/packed2. Screenshots17/18. Final read-only fixture comparison confirms both original WB/Ozon UUIDs, statuses and order counts unchanged ([after](artifacts/wms401-login-recovery-20260910/synthetic-documents-after.json)).

No additional lifecycle fix was made: the candidate did not reproduce a persistent blank screen in this bounded Android15 run. This does not establish the cause of the old v7 incident, hours-long suspension, or hardware-specific behavior.

## Remaining boundary

Physical ATOL/Android7/hardware scanner/printer58×40 not tested and not a candidate-readiness blocker under the latest owner instruction. No WMS-402 implementation in this repair. No production or public publication authorized here. One final root-owned review remains required; worker completion is not review acceptance or full WMS-401/412 closure.

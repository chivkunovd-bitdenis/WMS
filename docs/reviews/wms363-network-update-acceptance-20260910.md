# WMS-363 / WMS-401 / WMS-412 — actual app-button 9→10 acceptance

**PASS for the requested Android 15 emulator scope.** The existing emulator-5554
downloaded the published update through WMS, installed it through Android's system
confirmation, and retained the fixture account/PIN, server and original unfinished
documents. This report records new execution evidence, not the interrupted earlier
baseline attempt. Physical ATOL/scanner/printer acceptance is separate.

## Exact source, publication and installed packages

The full independent review
`wms415-coord/docs/reviews/wms363-apk-final-independent-review-20260910.md` was read.
It accepts Android commit beb2ba6dea046845e93c5c56c73963a7fb0ee117 and APK SHA-256
`cfe8b5adc1bbd62e728184b9a18a1e5a14a837b3028de865e493c6203bd36870`.
Source/artifacts were already delivered by main d5d8f5a5cbfcb22756ebea1f137e0f2029c63e33.
No product code or APK was changed/rebuilt in this acceptance pass.

The root publication marker appeared during useful baseline checks. Its verified
flag, versionCode 10, exact APK digest and immutable GitHub release URL matched
the authorized candidate; a safe copy is in publication-marker.json. Root published
the APK/manifest; this worker published neither. The marker names backend
0771833b7389260042f03a47abc7821e3a47fcb4; this worker's document checks used only
the isolated fixture on port 18083 and do not independently re-verify production.

Before the update, a filtered package query showed ru.wms.tsd versionCode 9,
0.1.8-wms401-orders-first. SHA-256 of the actual installed base.apk was
`ccb8d7ea57863133f1b2c0dc549ffb10c74d17620203ff0ba3f43f88726457a6`, matching public v9.
After Android's Update confirmation, the same package showed versionCode 10,
0.1.9-ozon-tsd, minSdk 24, targetSdk 35. The actual installed base.apk SHA-256 was
`cfe8b5adc1bbd62e728184b9a18a1e5a14a837b3028de865e493c6203bd36870` — exactly the
accepted published APK (45,624,909 bytes). before-package.json and after-package.json
record these independent installed-file checks. No auth/preferences/storage files
were read. The accepted APK's certificate SHA-256 is
`e343ab0cccc6284b271a72da42a67b14a0f0893d92b9ca461f1cac3d0be1aeb6`.

## Actual UI path

1. On v9, actual taps entered the existing fixture account using its known saved
   PIN. The visible server field remained http://10.0.2.2:18083/. No field was edited.
   WMS363-wb-unfinished opened with two orders and zero picked/packed progress.
   The v9 FBS worklist had no Ozon selector; its baseline document was WB.
2. After validating the root marker, tapped Проверить обновление once. WMS showed
   0.1.9-ozon-tsd, 43 MB and the published stale-box recovery release notes.
3. Tapped Скачать обновление once. Observed progress from 0% through 98%/100%, then
   the app explicitly reported that the download was complete and verified.
   No CDN retry, alternate URL, trust change or TLS bypass was needed.
4. Tapped Установить обновление. Android's PackageInstallerActivity displayed
   “Do you want to update this app?” and its Update button was tapped once.
   Installation returned to the Android launcher; WMS was opened by its visible
   launcher icon. No adb install, local-file substitution, uninstall or data clear
   was used anywhere in this acceptance pass.
5. On v10, the saved account still existed and the same PIN worked. The visible
   server field was unchanged. The update screen displayed 0.1.9-ozon-tsd. The
   original WB document reopened, then the newly available Ozon selector opened
   the original WMS363-ozon-unfinished document with two orders.
6. From that Ozon document, pressed HOME, waited 20 seconds, and tapped the WMS
   launcher icon. The same document and progress reappeared; the resumed component
   was ru.wms.tsd/.MainActivity. The fresh screenshot showed the document, not a
   white screen. This is one bounded background/resume check, not proof that every
   prior intermittent/physical-device white-screen cause is resolved.

## Server-form navigation observation

During the post-update server-field inspection, Back followed by the launcher icon
retained the password-login form. An attempted recents-card swipe also left that
form on reopening. To return to saved staff selection, this worker stopped only
the WMS process once with am force-stop, then reopened it by the launcher icon.
The saved staff picker and known PIN worked. No data was cleared and no credentials
were recreated. Network installation and exact installed-APK verification had
already succeeded before this extra process restart. This observation is recorded
separately from the successful ordinary HOME/20-second/resume cycle in step 6.
No App/auth code was changed or rebuilt to address this navigation observation.

## Original documents and data boundary

Read-only queries of the existing isolated fixture before and after matched
exactly on supply ID, name, marketplace, status and order count:

- WB 95b8355c-fb2f-4911-a0bd-8fce0021250e, WMS363-wb-unfinished, draft, two orders.
- Ozon 21e363e0-e6c6-49b6-8e80-92af50b3a982, WMS363-ozon-unfinished, assembling,
  two orders. Its absence from the v9 selector did not remove the backend document.

before-documents.json and after-documents.json record this comparison. No packing,
box assignment, handover or warehouse operation was tapped. No customer/protected
supply data was used or mutated. No PROGRESS, raw mobile events/logcat, tokens,
preferences, signing material or broad nested history was read. No desktop browser
or native-app focus was taken, no children were spawned and no coordinator files
were edited. Earlier untracked baseline files were preserved separately.

## Durable evidence and coordinator status

Evidence is under artifacts/wms363-network-update-20260910/. It includes the root
marker, installed-package hashes, document comparisons, bounded acceptance.json,
and screenshots of the baseline, version offer, downloaded/verified state, Android
confirmation, retained account/server, v10 version, both documents and resumed Ozon
document. Key before/after/installer screenshots were visually inspected.

WMS-412 actual network app-button 9→10 acceptance passed on this emulator. WMS-363
Ozon selector/original-document opening and WMS-401's scoped background-resume
check passed. Canon/status edits remain the coordinator's responsibility. Physical
ATOL, scanner, printer, 58×40 output and broader print-batch resource limits are not
accepted by this report. No code tests/build or full CI run is needed for this
report-only commit; prior implementation checks remain in the source follow-up.

# WMS-607: Direct Mac repair implementation, 07.10.2026

Product correction is saved for independent review and tester/analyst acceptance.
This developer verification is not release, installation or physical printer proof.

## Source selection and preservation

Work starts at the frozen test commit
`58eab40495a96b0d67d02ea6b537c044071cbccf`, from refreshed etalon.
The correct native base is `3348db9c61d62dfb8038be3b432a293f27ce9a1e`.
`git merge-base --is-ancestor 9a33b651c309796707053e1056c7f80dff7194d5 3348db9c6`
returns 0: journal3348 includes the public stable .4 dimensions and size-aware
receipt identity, plus the later journal recovery and rollback safety work.
Later WMS-660 commits restore the old native file rather than extending this
journal; choosing the latest whole branch would discard accepted features again.
The incident commit ed053 is also based on that old implementation.

Only `run` and `defaultPrinter` differ from the selected journal Swift blob.
All size validation, digest, media arguments, durable jobs-v2 storage, legacy
mirror/receipt import, unknown outcome handling, linked explicit reprints,
serialized submission and native self-tests are unchanged. Provenance and blob
SHA256 values are in `source-provenance.json`.
The exact same-source native dependencies (`wms_cups_observe.c`, `history.html`)
and existing native/observer tests are restored. No frontend/backend/Windows
runtime or printer configuration is changed.

## Correction

For resolver calls only, stdout is queue data and stderr remains diagnostic
terminal output. The exact reported default is validated by `lpstat -p name`;
no other printer is selected automatically. Error text cannot become a queue.
The default lookup, exact-queue validation and general-list timeouts each stop
with their actual cause before lp and before the legacy uncertain mirror.
The journal persists this known pre-submit failure; it remains safely retryable
with the same key after recovery/restart. Existing unknown outcomes remain protected.
All resolver failures use `PrintError.beforeSubmit`, matching the journal runtime.
Other run calls preserve their prior merged-output and bounded-process behavior.

## Verification on the actual candidate

No dependencies were installed. Native tests compile with the existing Swift and
C toolchains, redirect actual OS print command boundaries to executable fixtures
and use isolated stores. No host printer is touched.

- Frozen `test_macos_artmaks_contract.py`: 6/6 PASS, 18.925 seconds;
  `frozen-six-green.log`. All file bytes remain identical to the test commit.
  This includes three real Process timeouts; actual lp media=Custom.58x40mm;
  a receipt produced by the actual stable .4 source, read by candidate processes
  twice without resolver/lp; and rejection of changed dimensions before submission.
- Original five ed053 resolver regressions: 5/5 PASS, 2.947 seconds;
  `resolver-five-green.log`. The testcase methods and assertions are byte-identical.
  Only the harness is adapted: a full decodable PNG with 58/40 dimensions, the
  journal Printer record/process/retry API and the unused observer external symbol.
  The five assertions still require warning/localization preservation, distinct
  unavailable/stale outcomes, no uncertain legacy journal on failure, recovery
  and exactly one mocked submit. No expectation is relaxed.
- Existing journal3348 native tests: 3/3 PASS, 27.408 seconds;
  `native-runtime-green.log`. The actual optimized binary self-test covers crash
  exits, durable 350-job storage, disk failures, unknown response reconciliation,
  old/new journals, explicit copies, retry races, dimension checks and process
  timeout. The HTTP test covers legacy/protocol2 replay/restart and 350 distinct
  jobs sent twice; CUPS observer tests use fixture functions, never a host queue.
- `python3 -m py_compile` on build_console and the adapted parser harness passed;
  `git diff --check` passed. Existing dependency/source files are byte-identical
  to journal3348 as recorded in the provenance JSON.

## Exact build plan after review and acceptance

Use `.github/workflows/print-console-package.yml` with this implementation branch
and its reviewed exact SHA; it invokes `tools/print-agent/build_console.py`.
The mac-only build preparation compiles the restored CUPS observer, links it
with the native Swift source and libcups, and copies the matching history.html
beside wms-print. Windows build behavior remains unchanged. This is the same
native linkage exercised by the existing optimized native tests.

Do not use paired `build_package.py` or CI37511672771 as evidence for this repair.
Future Direct ARM/Intel package evidence must verify source_commit equals the
reviewed source SHA, runtime=direct, native executable architecture, signed
archive roundtrip/self-test, matching history asset and no embedded Python.
Compute/pin SHA256 only from those exact artifacts; source hashes here are not
archive checksums. Rosetta/native updater selection, unique previous-app archive,
atomic replacement/rollback and standard Gatekeeper/local-network permissions
remain a separate, unimplemented step using the independently reviewed installer
checks in dfc4c541. Existing journals/labels must survive that step.

No artifact, package, release, CI dispatch, updater, installation, Telegram message,
main merge or production change occurred. Independent review and original tester
acceptance of this exact source are required before packaging/client distribution;
physical paper, printer driver and client incident trigger are still unverified.

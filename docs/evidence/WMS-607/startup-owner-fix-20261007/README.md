# WMS-607: confirmed foreign owner during startup

Developer continuation in the existing permanent worktree; replacement developer identity remains separate from the unavailable original developer. Scope is the confirmed-foreign startup correction and these receipts. Independent review and analytical acceptance are pending.

Base: `a04a7b35f1e866c1283bdc46fff2d41eaf68b4d6`. Branch: `codex/wms607-startup-owner-fix-20261007`. Frozen test-first commit `7b94a8dd0f1d6a772272930df3894d3ccd299686` was cherry-picked before any product edit. Source-only fix: `7bbcdd8a8aba9fd44dd4ee4ce2dbdee5af26b880`, published and verified against the named remote branch before assembling this receipt.

`health_ok` now preserves the ownership classification returned by `owned_pid`. `start_owned` reports a confirmed foreign executable and returns nonzero immediately, before another sleep, poll, child wait, or health/readiness acceptance. No owner yet retains normal warmup, and the owned healthy case retains its actual health/readiness checks. No foreign process is signaled. The existing 50-poll window, sleeps, and immutable 15-second test deadline are unchanged.

Before editing the source, the actual additive suite reproduced **1 behavioral assertion failure and 2 preservation passes**, with zero errors/skips. The foreign case performed 51 port polls and 50 startup sleeps. With the correction it returns nonzero after the classification, with 2 port polls and zero startup sleeps; the current application, state and recovery intent remain unchanged in the fixture.

Final local results, each suite run once after the source change:

| Actual command suite | PASS | Failures | Errors | Skips | Raw result |
| --- | ---: | ---: | ---: | ---: | --- |
| Additive startup ownership | 3 | 0 | 0 | 0 | `green.xml`, `green.log`, `green/*.json` |
| Existing rollback stop | 4 | 0 | 0 | 0 | `rollback.xml`, `rollback.log`, `rollback/*.json` |
| Existing updater | 10 | 0 | 0 | 0 | `updater.xml`, `updater.log`, `updater/*.json` |
| Existing native/HTTP/resolver/ArtMaks | 19 | 0 | 0 | 0 | `existing.xml`, `existing.log`, `http/*.json` |

Exact commands (run from the worktree root; output captured in corresponding `.log` files):

```sh
WMS607_START_OWNER_RAW=docs/evidence/WMS-607/startup-owner-fix-20261007/precode python3 -B tools/print-agent/test_macos_direct_updater_start_owner_contract.py --report docs/evidence/WMS-607/startup-owner-fix-20261007/precode.xml
WMS607_START_OWNER_RAW=docs/evidence/WMS-607/startup-owner-fix-20261007/green python3 -B tools/print-agent/test_macos_direct_updater_start_owner_contract.py --report docs/evidence/WMS-607/startup-owner-fix-20261007/green.xml
WMS607_STOP_RAW=docs/evidence/WMS-607/startup-owner-fix-20261007/rollback python3 -B tools/print-agent/test_macos_direct_updater_stop_contract.py --report docs/evidence/WMS-607/startup-owner-fix-20261007/rollback.xml
WMS607_UPDATER_EVIDENCE_DIR=docs/evidence/WMS-607/startup-owner-fix-20261007/updater python3 -B docs/evidence/WMS-607/updater-test-contract-20261007/run-contract.py --report docs/evidence/WMS-607/startup-owner-fix-20261007/updater.xml
WMS607_HTTP_EVIDENCE_DIR=docs/evidence/WMS-607/startup-owner-fix-20261007/http python3 -B docs/evidence/WMS-607/updater-implementation-20261007/run-existing.py --report docs/evidence/WMS-607/startup-owner-fix-20261007/existing.xml
bash -n tools/print-agent/update_macos_direct.sh
python3 -B docs/evidence/WMS-607/startup-owner-fix-20261007/verify-receipts.py
```

`preservation.json` verifies every frozen additive contract file, original updater/rollback contracts, all existing print-agent files except the owned shell correction, the requirements document, the old runner, exact JUnit IDs, and raw source/test hashes against Git bytes. The verification script reads receipts without rerunning tests. The sparse checkout's existing runners were materialized from their unchanged Git blobs.

These are isolated local software checks with the frozen external fixtures and existing compilation tools/caches. No physical printing, customer installation, release publication, package build, broad CI, secrets management or chat send occurred. Both final architectures still require verification after independent rereview and distinct analytical acceptance. The historical Intel timeout remains a historical error; this local semantic correction does not establish its CPU/timing cause or turn the previous package run into a success. Authorization to continue eventual delivery to the exactly identified ArtMaks chat remains in force; this developer handoff does not claim delivery.

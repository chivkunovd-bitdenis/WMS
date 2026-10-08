# WMS-666 exact-candidate regression evidence

Candidate product source: `b6d23148f1571d08d13d83c6179c385e2f6a1efc` (`codex/wms666-packing-release-1008`). All three completed workflows below tested that exact candidate. The renderer artifact also records the immutable checked-out source, workflow commit and SHA-256 values for its runner and three renderer test files in `renderer-identity-b6d23148.json`.

## Focused suites

| Suite | Result | Run and artifact |
| --- | --- | --- |
| FBS main screen | 24/24 passed, including the Ozon XLS positions case | [run 37708207415](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37708207415), artifact `11521075644`; extracted `main24-b6d23148.json` has 24 passed records and no failures. |
| FBS picking, base | 29/29 passed, zero failed or blocked | [run 37708207401, attempt 2](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37708207401), artifact `11520901036`; `picking-base-b6d23148.json` includes expected cases and exact app/test SHA. |
| FBS picking, extended | 40/40 passed, zero failed or blocked | [run 37708207401, attempt 2](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37708207401), artifact `11521406217`; `picking-extended-b6d23148.json` includes expected cases and exact app/test SHA. |
| Linux Chromium / print renderer | WMS-672/673 rendered suite passed; WMS-657 C1–C6 6/6; WMS-673 DOM 19/19; WMS-673 PDF 5/5; strict aggregator passed with all required cases executed | [run 37709255731](https://github.com/chivkunovd-bitdenis/WMS/actions/runs/37709255731), artifact `11521810599`. The immutable workflow commit, checkout SHA and source file hashes are in `renderer-identity-b6d23148.json`; runtime versions are Node 24.21.0, Chromium 141.0.7390.37, Playwright 1.56.1 and Poppler 24.02.0. Full individual Vitest JSON records are adjacent. |

The picking run was first red only because installing Playwright's Ubuntu browser dependencies exceeded its three-minute step timeout before the extended tests began. The retry executed only the failed job; the base shard was already green and was not repeated. On retry the install completed, and the extended real frontend/API/database/worker suite passed all 40 cases. This was an infrastructure timeout, not a product assertion failure.

## Evidence boundary

These focused checks do not establish completion of the broader CI or physical-printer acceptance. The separate generic CI run is still needed after independent acceptance/source review. Its `print-regressions` job contains native print-error, peer-drain, raster, and CDP-cancellation checks, `run_release_print.sh`, and the critical FBS browser journey (QR input, continuous printing, selected-order buttons); its Windows job covers print receipt/recovery. The generic workflow also includes the full PostgreSQL and guard suites. No generic CI, deploy, merge, printer-device or warehouse-operator acceptance is claimed here. The current-candidate renderer workflow was successful on Linux; it is not evidence that a physical printer produced paper.

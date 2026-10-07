# WMS-652: final infrastructure bootstrap source pin

**APPROVED: the exact bootstrap BASE/SOURCE pair below, for the configuration source pin and prepared candidate.** No blocking defect was found in this bounded identity, protection-retention and acceptance-handoff review. This is independent Sol6.1/high reviewer session `01a11389-3a47-7ec0-b74c-b8d920bfcca8`. It does not approve a successful full CI, main configuration activation, release or deployment.

| Pin | Immutable value |
| --- | --- |
| BASE | `4b298efc95be7b4b6b7fe5665be9f3671f1fe747` |
| SOURCE | `321f69385a8783bbf0c2fa65e80829e4c9c32373` |
| SOURCE policy SHA256 | `1dced9197f99a8922ca6d10795fab51a02c48ebd821e90fc686ac56860caa2eb` |
| Accepted static product reference | `25ebc6fe13384a55cf1f2b7e5e4054bb862d002d` |

The BASE is an ancestor of SOURCE and has no `guards/PROCESS_CONTRACTS.json`; this is the explicitly authorized bootstrap pair. Historical approval of SOURCE `9dae4b19f6d4dca554200e08282579414a110848` remains historical. The installed main pin has not been changed by this review.

The offline [probe](source-probe.py) reads actual immutable Git blobs and tree modes, rather than sparse working-tree files. Its [JSON result](source-probe.json) confirms **230 regular protected files**, with **223 mode100644 and 7 mode100755**, all matching their policy SHA256. No protected path is absent or a symlink/submodule. There are **22 suites and 1180 case IDs**, with no duplicate IDs within a suite. The canonical actual-file accounting rows have SHA256 `f30efb696a5156a433a3eced4bceec2608dd31f4247af4a8f65dafdb675e18ac`.

All protected blobs, modes, policy bytes and suite definitions are identical to previously reviewed SOURCE `972da18be97cab8c41b14b0aa00a3d30773e4492`. The complete intervening Git delta contains only documents, enumerated in the JSON. All 229 paths and 21 complete suite definitions/1173 IDs from historical9dae are retained; the only added protected path and suite are the frozen CDP test and its exact seven-case `node-tap` report. All 210 paths and 955 IDs from baseline `93b0757103fbd29fb00d4f198f6baab8def85172` retain modes, existing case order and suite metadata; previously reviewed additive cases remain present. The detailed before/after digest accounting is saved in JSON.

Existing protected digest migrations since9dae are precisely:

| Path | Retained independent justification |
| --- | --- |
| `scripts/ci/tests/test_ci_release_additions.py` | Literal accepted reference d618→immutable25eb, already PASS in ab0; no assertion weakening. |
| `backend/tests/test_prod_deploy_backup_gate_boundary.py` | Portable full-field AST serialization with the single fixed063 digest, already PASS in3850; original23 asserts/seven variants preserved. |
| `.github/workflows/ci.yml` | One additive Node CDP command/report, already PASS in853; current command bytes unchanged since that review. |
| `frontend/tests-e2e/wms652-critical/browser.mjs` | Finite class-owned cancellation handling and live ambiguity recheck, PASS/R1 CLOSED in7c467. |

The older93 changed-path set remains exactly workflow, browser fixture, its `cases.json`, and the two Mac helper tests: the already reviewed geometry/Mac/CI migrations, with the later bounded browser correction. No other old protected digest changed. The new CDP test SHA256 is `53c54d384299e90ad3c2892ccb6c611995ffeee14bda2f5bf251b6cd0a21ad20`, byte-identical to separate testwriter `d0242bb882290daadd59e5a38e678392d3a520a3`; browser SHA256 is `24f146ba0e038645114edb882a85686dc834f8c338d1324c10426b7648bd6dd6`, byte-identical to developer fix `307873b739c879a7e322275efc223f0069b47745`. Both packages and all four closure paths remain protected. The exact seven IDs, report `print/wms652-cdp-cancellation.tap`, format and strict `exact:true` definition are saved in JSON. The unchanged workflow command at line299 feeds the previously reviewed artifact/process-proof pipeline; its static product reference remains25eb at line388.

The product comparison to25eb still has only the previously reviewed CryptoPro `.test.ts` title infrastructure difference, with no production application delta. Frozen scope51/script, strict report parser, backup source, original43 business cases/routes/assertions/delays, C5, native7/peer2/raster3 and all prior report commands are retained by the immutable accounting and prior reviews. No new ignored exception, required skip, case removal or reduced Mac110/browser43 count is accepted here.

The **distinct** analyst acceptance commit `ff6110eebc0ca1d39c1f2308e1141420e5853d79` names SOURCE972da and independent review `7c4670975d7e70cbbfe28fb0cd4ee66f39018007` with PASS/R1 CLOSED. Its acceptance JSON is byte-identical in this SOURCE (SHA256 `4fa190faf67ce3caa86a0a8a81430c792d74e7e85487e3795eee9c7a73ec36c9`), as are its README, WMS-652 requirements and backlog. The published7c review is likewise retained byte-for-byte. Protected SOURCE equivalence and this unchanged actor acceptance justify the final pin transfer; the reviewer does not substitute for analytical acceptance. Prior3850/5c6/853/7c findings remain intact; bef38 is superseded only for the resolved R1.

No tests, builds, browser sessions, CI jobs, requirements checks or artifact downloads were repeated. Previously reviewed target7 PASS/0 skip, measured abort controls, Node/geometry/Mac receipts and original CI raw evidence retain their historical meaning. The original unlogged CI interception cause remains **UNKNOWN**. Historical run37548248403 attempt1, tested merge `ac845328b27b5be265962695e10766efddef339e`, failed after743 seconds; that is not a successful10–15-minute result, and an unexecuted PostgreSQL stage is not PASS. Actual full43 effectiveness after the fixture patch and the exact final candidate's **full common CI remain required next**. There is no new C5 run or trace-loss condition.

This approval permits the integrator's ordinary configuration-only main PR to install this exact pair, followed by the mandatory final candidate CI. It supplies no proof of main pin activation, successful full CI, etalon promotion, staging/production image identity, provider operation or physical printing. Those outcomes were neither executed nor claimed by this reviewer.

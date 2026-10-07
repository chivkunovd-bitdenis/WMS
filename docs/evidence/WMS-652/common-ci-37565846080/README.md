# Final common CI 37565846080

Actual attempt 1 on PR head `1e14876e35f0f7202a4e3875082e95201af56b5b`, tested merge `64aef1d0b2316c3d97904c6b507c5df33fcaf463` (BASE `4b298efc95be7b4b6b7fe5665be9f3671f1fe747`), completed SUCCESS at 03:27:39 UTC on 2026-10-07. Elapsed 773 seconds (12m53), including proof production; the owner target 10–15 minutes is met for this successful run.

All 22 policy suites / 1192 required IDs passed, including all 627 required backend cases without skips, 37 required PostgreSQL cases and all 43 unchanged browser cases. Exact two-shard receipts and JUnit merge prove all 4643 collected backend cases executed once: 4445 passed, 198 ordinary skips, no failures/errors. See full-raw-verified.json and original raw files. Full collection is preserved; ordinary skips do not waive any mandatory case.

The actual process-proof artifact 11458234741 carries exact tested SHA, PR head, BASE, run ID, attempt and accepted policy digest. Independent latest published process-integrity check 112616517605 is SUCCESS at 03:28:10 UTC. Ordinary PR merge was nevertheless refused while the initial pull_request_target anchor workflow job remained failed in the rollup. Only that trusted anchor run 37565846149 is re-run after completion; no full CI retry or candidate modification. Merge, etalon-push CI and deployment remain separate pending steps.

Staging-before.json independently confirms all four staging services still on cc8e6a0; production readonly checkout remains 8f11d91. No runtime changes claimed here.

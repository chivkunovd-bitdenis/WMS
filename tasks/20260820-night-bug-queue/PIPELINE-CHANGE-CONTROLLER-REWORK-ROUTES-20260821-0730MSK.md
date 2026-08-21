# Pipeline change: controller rework routes

Timestamp: 2026-08-21 07:30 MSK
Wave: wave-a1b311d18f07
Branch: codex/wms-pipeline-unified-v2-20260820
Scope marker: PIPELINE_SCOPE_ALLOW: pipeline_change

## Why this is a control-plane patch

The night wave reached critical controller blockers unrelated to BA/Product/Research/Architect judgment:

- BLG-I08: `PRODUCT_REJECTED` correctly selected S09, but controller invalidated accepted S01-S04 receipts and packet/next fell back to S01.
- BLG-J02: `REQUIRED_CASE_WITHOUT_BINDING` correctly selected S19, but controller invalidated accepted S01-S19 receipts and packet/next lost the accepted chain.
- BLG-D22: S14 produced architecture rework, but controller had no `ARCH_REVIEW_REWORK` route back to S13.

Pipeline v2 says that if prose and machine state disagree, the affected transition must stop and the contract/controller must be repaired. This patch repairs only controller mechanics; it does not approve any task artifact, does not run Dev, does not release, and does not touch production.

## Change

1. Failure-route invalidation with a `resume_stage` now preserves accepted predecessor receipts and invalidates only the owning stage plus downstream stages.
2. Profile/input changes without a `resume_stage` still invalidate the full accepted chain.
3. `ARCH_REVIEW_REWORK` is mapped to `S13`/`REWORK` in the controller and policy metatest map.

## Boundaries

- No live deploy.
- No production change.
- No live WB/Ozon call.
- No secrets or key cabinets.
- No release for BLG-C01/BLG-C02.
- No manual rewrite of damaged task states.
- No claim that already damaged BLG-I08/BLG-J02 histories are repaired by this code patch alone.

## Verification

Commands run:

```bash
python3 scripts/ci/check_pipeline_policy_metatests.py
python3 scripts/ci/check_pipeline_metatests.py
python3 scripts/pipeline/run.py validate
python3 scripts/ci/check_pipeline_scope_guard.py --changed-path pipeline/controller.py
PIPELINE_SCOPE_ALLOW=pipeline_change python3 scripts/ci/check_pipeline_scope_guard.py --changed-path pipeline/controller.py
```

Observed results:

- policy metatests passed;
- pipeline metatests passed;
- controller validate passed;
- scope guard rejected protected path without explicit authorization;
- scope guard accepted the same path with `PIPELINE_SCOPE_ALLOW=pipeline_change`.

## Next legal actions

1. Commit this controller patch with the `PIPELINE_SCOPE_ALLOW: pipeline_change` marker.
2. Use controller commands only for any affected task transitions.
3. For BLG-D22, route `ARCH_REVIEW_REWORK` through controller once the patch is committed.
4. For BLG-I08 and BLG-J02, do not replay accepted stages manually; prepare a controller replay/repair artifact if their prior receipts must be restored.

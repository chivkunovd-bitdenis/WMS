# Wave a1b311d18f07 waiting normalization

Timestamp: 2026-08-21 07:36 MSK
Branch: codex/wms-pipeline-unified-v2-20260820

## What changed

The controller no longer reports any BLG card as `RUNNING` when the next legal stage cannot continue:

- BLG-D16 moved from `RUNNING S10` to `WAITING S10` with `BUDGET_HARD_STOP`.
- BLG-D20 moved from `RUNNING S11` to `WAITING S11` with `BUDGET_HARD_STOP`; existing `BLK-INTEGRATION-001` remains in `blocked_by`.
- BLG-I05 moved from `RUNNING S11` to `WAITING S11` with `BUDGET_HARD_STOP`.
- BLG-I15 moved from `RUNNING S11` to `WAITING S11` with `BUDGET_HARD_STOP`.
- BLG-J04 moved from `RUNNING S11` to `WAITING S11` with `BUDGET_HARD_STOP`.
- BLG-F01 moved from `RUNNING S16` to `WAITING S16` with `F01_CASE_AUDIT_REQUIRED_BEFORE_PRODUCT_S16`.
- BLG-D09 moved from `RUNNING S18` to `WAITING S18` with `BLK_RELEASE_001_RELEASE_CHANGE_DEV_HELD`.

Fresh packet and dispatch files were regenerated after each hold so handoff prompts now carry the actual `WAITING` status and blocker data.

## Result

Controller count after normalization:

- WAITING: 49
- RUNNING: 0

This is not completion of the backlog. It is the correct stopped state for the wave: no worker is falsely shown as active, and no expensive Product/Architect/Review stage is invited to continue while the wave has no owner budget override.

## Next action

Resume requires one of:

- owner budget override with marker `PIPELINE_BUDGET_OVERRIDE: owner-approved`, reason, new limit and expiry;
- lower-scope decision recorded as a pipeline artifact;
- closure artifact for the non-budget blockers, such as BLG-F01 case-auditor PASS or BLG-D09 release proof.

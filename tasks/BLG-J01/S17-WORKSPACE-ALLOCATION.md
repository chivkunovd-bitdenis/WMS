# S17 WORKSPACE_ALLOCATION - BLG-J01

## Verdict

`WORKSPACE_READY`.

## Allocation

- Task id: `BLG-J01`
- Branch: `codex/wms-pipeline-unified-v2-20260820`
- Worktree: `/Users/deniscivkunov/Projects/WMS/.worktrees/pipeline-unified-v2`
- Evidence directory: `docs/evidence/BLG-J01/`
- Celery queue: `wave-a1b311d18f07-blg-j01`
- Database/Redis/emulator namespace: local wave-scoped controller values from `tasks/BLG-J01/state.json`

## Dev Scope

The Dev worker may implement only the approved low-risk UI change: add a clear label for the already displayed six-character KIZ tail in the FBS order marking dialog. The implementation must preserve scanner cadence and cannot change API, parser, persistence, database, worker, marketplace, print or authorization behavior.

## Required Inputs For Dev

- `tasks/BLG-J01/S09-UX-CONTRACT.md`
- `tasks/BLG-J01/S11-PRODUCT-CONTRACT.md`
- `tasks/BLG-J01/S12-TASK-CUT.md`
- `tasks/BLG-J01/S15-CASE-FACTORY.md`
- `tasks/BLG-J01/S15-CASES.json`
- `tasks/BLG-J01/S15-CASE-AUDIT.md`
- `tasks/BLG-J01/S16-PRODUCT-BEFORE-DEV.md`

## Isolation Rules

- Do not touch unrelated BLG tasks or shared release/prod artifacts.
- Do not perform live WB/Ozon calls, deploy, prod changes, secret access or release actions.
- Keep changes scoped to the existing FBS marking dialog/UI-kit surface required by the approved artifacts.
- Preserve all existing unrelated dirty worktree changes.

Agent identity: `codex-night-orchestrator-dispatcher`

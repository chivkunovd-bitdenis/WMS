## Summary

-

## Pipeline v2

Pipeline v2 is `ACTIVE`. Canon: `docs/process/PIPELINE-RU.md`; machine contract:
`pipeline/pipeline.yml`.

| Field | Value |
|---|---|
| Task ID | |
| Backlog ID | |
| Base SHA | |
| Final SHA | |
| Current/final stage | |
| Controller validation | |
| Blockers | none / IDs |

Required receipts and evidence:

- [ ] Product/BA contract approved before development
- [ ] Architecture/Research receipts present when required by traits
- [ ] Executable cases bound to the task
- [ ] Independent code review passed
- [ ] Functional and integration stages passed
- [ ] Live visible-browser Product QA passed when required
- [ ] Result committed and pushed; evidence paths contain no secrets
- [ ] Release authorization recorded separately, or release is explicitly out of scope

## Test coverage

Required for changes under `frontend/src`, `frontend/tests-e2e`, `backend/app/api` or
`backend/app/services`. Include at least two TC rows, one applicable row, Given/When/Then and a
negative or restriction case.

| TC-ID | Title | Applies (Y/N) | Notes |
|---|---|---|---|
| TC- | | Y | Given ... When ... Then ... |
| TC- | | N | Negative/restriction: ... |

## Verification

- [ ] `python3 scripts/pipeline/run.py validate --task-id <TASK_ID>`
- [ ] Relevant backend checks
- [ ] Relevant frontend checks
- [ ] Required browser/evidence receipts

## Notes / risks

-

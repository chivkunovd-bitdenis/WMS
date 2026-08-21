# AGENTS

## Active Pipeline v2

Pipeline v2 is the only active process for new WMS work. The human-readable canon is
[docs/process/PIPELINE-RU.md](docs/process/PIPELINE-RU.md), and the machine contract is
[pipeline/pipeline.yml](pipeline/pipeline.yml). If prose and machine state disagree, stop the affected
transition and repair the contract; do not invent a local process.

Every task must be opened or imported into the controller and then move through its declared stages,
receipts, blockers and evidence. A backlog title alone is not a specification: use the complete
`backlog_item.business_meaning`, Product/BA contracts and executable cases. The retired narяд and
legacy Product-gate documents are historical pointers and are not alternative routes.

Basic commands:

```bash
python3 scripts/pipeline/run.py status --task-id <TASK_ID>
python3 scripts/pipeline/run.py next --task-id <TASK_ID>
python3 scripts/pipeline/dispatch.py --task-id <TASK_ID> --executor codex
python3 scripts/pipeline/run.py validate --task-id <TASK_ID>
python3 scripts/pipeline/run.py report
```

For a user-approved backlog wave, use `start-wave` with IDs from
[docs/product/backlog-queue.json](docs/product/backlog-queue.json). Do not start Dev before the
controller has passed the required Product, Research, Architecture and case stages.

## Hard Boundaries

- Do not deploy, merge or push to `etalon` without a separate explicit owner instruction.
- Do not open, create, rotate, replace or remove credentials or secrets without a separate explicit
  request naming that action and its purpose.
- Preserve unrelated and uncommitted work. Never delete another task's diff or use destructive Git
  commands to make the tree look clean.
- `DONE` requires the committed and pushed result, required tests, independent review and the final
  acceptance receipts declared by the task profile. Local code or a green partial test is not done.
- Production truth requires exact SHA, artifact/digest proof and live verification. A local URL or
  successful build is not deployment evidence.
- External marketplace operations, production data changes and release actions remain separately
  authorized even though the process status is `ACTIVE`.

## Repository Rules

Repository paths, branches, environment safety, backend layers and verification commands are in
[CLAUDE.md](CLAUDE.md). Product terminology comes from [docs/MVP_DECISIONS_RU.md](docs/MVP_DECISIONS_RU.md).

Backend layers stay separate: routes in `backend/app/api`, business logic in
`backend/app/services`, models in `backend/app/models`, database access in `backend/app/db`, and
background work in `backend/app/tasks`. New routes require behavior tests; migrations are additive
unless the owner separately approves destructive data work.

Frontend work uses [frontend/src/ui-kit/](frontend/src/ui-kit/) and the UX canon in
[docs/product/UX_CANON_RU.md](docs/product/UX_CANON_RU.md). New or touched operator flows require
live visible-browser Product QA at the stage declared by the controller; Playwright, curl and code
reading are supporting evidence, not a substitute for that verdict.

## Reporting

Report the controller truth: task ID, backlog ID, current stage, role, blocker, next action, commit
SHA, push state and evidence path. Keep local, committed, pushed, deployed and browser-accepted
states distinct.

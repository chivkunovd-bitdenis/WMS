---
name: wms-pipeline-autopilot
description: Run or coordinate a WMS Pipeline v2 task through its controller stages, receipts, and independent role checks. Use for WMS pipeline work only, not general coding or unrelated project management.
---

# WMS Pipeline Autopilot

Use this skill for a WMS task that is being opened, routed, advanced, validated, reviewed, or accepted through Pipeline v2. It is not a generic implementation workflow.

## Start From the Controller

Read `AGENTS.md`, `docs/process/PIPELINE-RU.md`, and `pipeline/pipeline.yml` before acting. Treat `pipeline/pipeline.yml` as the machine contract and `pipeline/controller.py` as the command behavior.

Use the wrapper, not hand-edited state or receipts:

```bash
python3 scripts/pipeline/run.py next --task-id <TASK-ID>
python3 scripts/pipeline/run.py packet --task-id <TASK-ID>
python3 scripts/pipeline/run.py hold --task-id <TASK-ID> --blocker-type OWNER_INPUT --reason-code <CODE> --reason "<reason>" --resume-condition "<condition>"
python3 scripts/pipeline/run.py resume --task-id <TASK-ID> --by owner
python3 scripts/pipeline/run.py advance --task-id <TASK-ID> --stage <STAGE> --verdict <VERDICT> --role <ROLE> --agent <AGENT>
python3 scripts/pipeline/run.py validate --task-id <TASK-ID>
```

Before each handoff or `advance`, run `next`; advance only the stage it reports and only for the role that owns it. Use `packet` to create the handoff artifact. `validate` is required before reporting the controller state as valid.
If `next` or `status` shows `WAITING`, stop: do not run `advance`, report the blocker and resume condition, and wait for explicit owner `resume`.

When `scripts/pipeline/dispatch.py` is present, create a Codex handoff prompt with:

```bash
python3 scripts/pipeline/dispatch.py --task-id <TASK-ID> --executor codex
```

## Stage Boundaries

Do not fix a reported bug before the owner-approved Product-before-Dev stage permits development. A bug report still follows the current pipeline stage unless the owner explicitly authorizes an emergency path.

Do not accept your own implementation as Product, Reviewer, or Browser Product. Product Browser acceptance for an operator-visible flow is a real, visible browser walkthrough on the exact accepted artifact; Playwright, API checks, screenshots, and code review do not replace it.

Do not set or describe a task as `DONE` while `pipeline/pipeline.yml` is not `ACTIVE`. Until then, report only the controller status actually reached, such as `IMPLEMENTATION_DONE` or `READY_FOR_RELEASE`.

## Codex Multi-Agent Work

When the user has authorized agents, Codex may delegate a bounded stage to a worker or explorer. Give each subagent a disjoint file or evidence scope, the current packet, and its expected output; keep stage ownership independent so an agent does not approve its own work. Subagents must not push or commit unless the user explicitly instructs it.

## Operational Limits

Never hand-edit `.pipeline-state/**`, task state, or receipts. Do not touch secrets, live deployments, or Wildberries/Ozon systems as part of this skill. Those actions require separate explicit user authorization.

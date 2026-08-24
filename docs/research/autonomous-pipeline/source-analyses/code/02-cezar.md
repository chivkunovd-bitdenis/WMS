# Cezar — code-level reverse engineering

Pinned commit: [`185c68a7af58d8c05381a20ebc6d4b2ac1b26be9`](https://github.com/open-mercato/cezar/tree/185c68a7af58d8c05381a20ebc6d4b2ac1b26be9), read 2026-08-24 via GitHub pinned tree/raw API. A full temporary clone was attempted but did not finish before network timeout; every claim below is restricted to pinned files and tests. E1 for local state/scheduler, not an unattended delivery system.

## Component map and persisted schema

`runs/store.ts` owns `runs.json`; `runs/event-history.ts` projects NDJSON history; `runs/review-gate.ts` decides terminal review; `automations/{store,github-poller,scheduler}.ts` implement durable GitHub detection/launch. Run statuses are exactly `queued | running | waiting | review | done | failed | cancelled` ([store L14–15](https://github.com/open-mercato/cezar/blob/185c68a7af58d8c05381a20ebc6d4b2ac1b26be9/packages/cezar/src/runs/store.ts#L14-L15)); step statuses also add `pending`/`skipped` ([L25–33](https://github.com/open-mercato/cezar/blob/185c68a7af58d8c05381a20ebc6d4b2ac1b26be9/packages/cezar/src/runs/store.ts#L25-L33)). Persisted records include task/workflow/status, runner/model/session-profile affinity, diff stat, tokens/cost, PR discovery and optional auto-resume deadline/attempts ([L96–184](https://github.com/open-mercato/cezar/blob/185c68a7af58d8c05381a20ebc6d4b2ac1b26be9/packages/cezar/src/runs/store.ts#L96-L184)).

## Happy path and transition table

| From | To | Code condition | Evidence |
|---|---|---|---|
| queued | running | scheduler/runner dequeues; queued messages fold into initial task | [L76–86](https://github.com/open-mercato/cezar/blob/185c68a7af58d8c05381a20ebc6d4b2ac1b26be9/packages/cezar/src/runs/store.ts#L76-L86) |
| running | waiting | agent attention boundary; monitoring is a running substate | [L16–24](https://github.com/open-mercato/cezar/blob/185c68a7af58d8c05381a20ebc6d4b2ac1b26be9/packages/cezar/src/runs/store.ts#L16-L24) |
| successful terminal | review | changed worktree + review gate + non-autonomous | [review gate](https://github.com/open-mercato/cezar/blob/185c68a7af58d8c05381a20ebc6d4b2ac1b26be9/packages/cezar/src/runs/review-gate.ts#L1-L22) |
| successful terminal | done | gate off/no diff/autonomous | same implementation/tests |
| error | failed | runner/store error; optional persisted provider-limit resume | [L159–184](https://github.com/open-mercato/cezar/blob/185c68a7af58d8c05381a20ebc6d4b2ac1b26be9/packages/cezar/src/runs/store.ts#L159-L184) |

The cancellation call site and complete workflow-step graph were not recovered: they remain unknown, not inferred.

## Retry, prompts, Git, scope and acceptance

The concrete automation loop takes a lease, reads cursor, reserves a durable receipt before launch, records `launched`/`launch-error`, and backs off failure exponentially from 60 seconds to six hours ([scheduler L29–111](https://github.com/open-mercato/cezar/blob/185c68a7af58d8c05381a20ebc6d4b2ac1b26be9/packages/cezar/src/automations/scheduler.ts#L29-L111)); it serializes GitHub requests and does not poison later requests after one rejection ([L13–24](https://github.com/open-mercato/cezar/blob/185c68a7af58d8c05381a20ebc6d4b2ac1b26be9/packages/cezar/src/automations/scheduler.ts#L13-L24)). History has first-class lifecycle/error/check-output/ask events ([history L54–77](https://github.com/open-mercato/cezar/blob/185c68a7af58d8c05381a20ebc6d4b2ac1b26be9/packages/cezar/src/runs/event-history.ts#L54-L77)). Prompt templates, semantic test acceptance, file allow-list, automatic merge/PR approval and hard budget enforcement were not proven in inspected code.

## WMS verdict

Adapt durable state, receipt-before-launch, bounded scheduler backoff and session/profile affinity. Do not adopt as a whole: `autonomous` intentionally bypasses waiting and terminal review ([L141–148](https://github.com/open-mercato/cezar/blob/185c68a7af58d8c05381a20ebc6d4b2ac1b26be9/packages/cezar/src/runs/store.ts#L141-L148)); no independent browser gate or contract-to-test enforcement was found.

## Tests

- [review-gate tests](https://github.com/open-mercato/cezar/blob/185c68a7af58d8c05381a20ebc6d4b2ac1b26be9/packages/cezar/src/runs/review-gate.test.ts)
- [scheduler tests](https://github.com/open-mercato/cezar/blob/185c68a7af58d8c05381a20ebc6d4b2ac1b26be9/packages/cezar/src/automations/scheduler.test.ts)

# DoorDash agentic-orchestrator — reverse engineering result

Pinned commit: [`e2e61837ece2e89899d1ca600ef02b9a3a25423f`](https://github.com/doordash-oss/agentic-orchestrator/tree/e2e61837ece2e89899d1ca600ef02b9a3a25423f), inspected 2026-08-24 using pinned tree/API; clone did not complete before network timeout. E1 only for the desktop review-client path below. The repo contains CLI, desktop and server-adjacent packages, so README-level claims were not promoted to architecture facts.

## Verified component map, schema and path

The recoverable controller is `desktop/src/main/reviews.ts`; it calls a feature-scoped reviews endpoint. A client creates a session via `POST features/{featureId}/reviews`, reads/saves draft state and supplies optimistic `base_revision` ([L61–80](https://github.com/doordash-oss/agentic-orchestrator/blob/e2e61837ece2e89899d1ca600ef02b9a3a25423f/desktop/src/main/reviews.ts#L61-L80)). Component map: desktop IPC/main process → API client/schema validation → server review session/draft. The observable happy path is create review → fetch/edit draft → save against revision → receive updated revision or conflict. This is revisioned human-review data, not a coding-run state machine.

## Transitions and controls

| From | To | Decision owner | Evidence |
|---|---|---|---|
| no review | review session/draft | client POST after request schema validation | [reviews L61–80](https://github.com/doordash-oss/agentic-orchestrator/blob/e2e61837ece2e89899d1ca600ef02b9a3a25423f/desktop/src/main/reviews.ts#L61-L80) |
| draft revision N | draft revision N+1 | server accepts update whose `base_revision` is current | same API path |
| stale draft | conflict/error | server-side optimistic concurrency | base revision contract |

Tests exist for the client ([reviews tests](https://github.com/doordash-oss/agentic-orchestrator/blob/e2e61837ece2e89899d1ca600ef02b9a3a25423f/desktop/src/main/__tests__/reviews.test.ts)). Server schema, conflict status code, run queue, retry/resume and merge code were not established by the files read. Prompts, agent artifacts, worktrees, PR state, scope control, budget, test/browser acceptance are therefore explicit unknowns.

## WMS verdict

Adapt only the narrow pattern: an independently persisted review verdict can be revisioned to prevent silently overwriting a concurrent judge. Reject this source as evidence for autonomous overnight orchestration: a review UI/API is not controller state, and no plan→code→test→merge transition graph was proven.

## Evidence

- [review client implementation](https://github.com/doordash-oss/agentic-orchestrator/blob/e2e61837ece2e89899d1ca600ef02b9a3a25423f/desktop/src/main/reviews.ts#L1-L140)
- [client tests](https://github.com/doordash-oss/agentic-orchestrator/blob/e2e61837ece2e89899d1ca600ef02b9a3a25423f/desktop/src/main/__tests__/reviews.test.ts)

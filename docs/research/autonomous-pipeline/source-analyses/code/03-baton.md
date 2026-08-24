# Baton — детальный reverse engineering

Проверено 2026-08-24 на HEAD [`7bb5fb73c08f31d897b7b64e85b3247a0292eebd`](https://github.com/mraza007/baton/tree/7bb5fb73c08f31d897b7b64e85b3247a0292eebd). Уровень E1: Python controller/state/workspace/worker/prompt и unit tests. Это GitHub-Issue → Claude Code → PR runner, не product/UX pipeline и не browser judge.

## Компоненты и хранимое состояние

`Orchestrator` собирает `GitHubTracker`, `WorkspaceManager`, `Worker`, config и `OrchestratorState` ([constructor](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/orchestrator.py#L18-L37)). `IssueState` хранит issue id/title/tracker-state, текущий `turn`, `max_turns`, timestamps/error; `RetryEntry` — attempt/due_at/error. Контейнеры: `running`, `claimed`, `retry_queue`, `completed` ([state schema](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/state.py#L11-L41)). `persist` пишет JSON snapshot running/retrying/claimed и только `completed_count` ([L81–109](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/state.py#L81-L109)); `load`/replay в изученном коде нет, значит restart-resume не доказан.

| State | Реальное хранение | Переход |
|---|---|---|
| candidate | GitHub tracker | `_should_dispatch` при not-claimed + available slot |
| running/claimed | two state containers + asyncio task | `_dispatch` |
| retry queued | `RetryEntry` | error, no PR, poll failure/no slot |
| completed/released | completed set, then `release` | PR exists |
| cancelled/released | containers cleared | reconcile sees closed issue |

## Happy path по функциям

`_tick` starts reconcile/retries and reloads config ([L240–259](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/orchestrator.py#L240-L259)). `_dispatch` creates `IssueState(turn=1,max_turns=...)`, claims it and creates worker task ([L39–62](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/orchestrator.py#L39-L62)). `_run_worker`: (1) `ensure_worktree`; (2) `after_create` only new tree; (3) mandatory `before_run`; (4) parse issue skills; (5) call model up to max turns; (6) `after_run`; (7) `check_pr_exists` ([L102–182](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/orchestrator.py#L102-L182)). Callback marks `pr_created` complete+releases claim, otherwise queues one-second continuation and persists ([L64–96](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/orchestrator.py#L64-L96)).

## Failures, retry, reconcile

| Condition | Exact transition | Bound |
|---|---|---|
| hook/agent exception | callback → retry with `min(10s*2^(attempt-1), max_retry_backoff_ms)` | only backoff cap ([L73–100](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/orchestrator.py#L73-L100)) |
| success but no PR | retry attempt=1, 1s | no global retry cap |
| retry poll fails | attempt+1/backoff | preserves claim ([L208–222](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/orchestrator.py#L208-L222)) |
| issue no longer candidate | release | worktree not cleaned in this path ([L224–228](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/orchestrator.py#L224-L228)) |
| no slot | attempt+1/backoff | preserves retry ([L230–238](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/orchestrator.py#L230-L238)) |
| tracker says closed while running | cancel task, release, cleanup worktree | tracker error leaves worker unchanged ([L184–206](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/orchestrator.py#L184-L206)) |
| CLI timeout | kill process, WorkerResult error/−1 → retry | turn timeout ([worker L99–120](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/worker.py#L99-L120)) |

Thus outer retry can grow indefinitely: a concrete absence of loop budget.

## Prompts, execution and artifacts

First prompt is configured Jinja template rendered as `issue=asdict(issue), attempt`; `StrictUndefined` makes missing values a hard error ([prompt L17–40](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/prompt.py#L17-L40)). Every later turn gets literal: “Continue working… Check what's been done… If the work is complete, commit, push, and create a PR.” ([L132–140](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/orchestrator.py#L132-L140)). Worker invokes `claude -p … --output-format json`, distinguishes `is_error`, nonzero exit, timeout and missing executable ([L52–72](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/worker.py#L52-L72), [L122–166](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/worker.py#L122-L166)). Artifacts: issue, PR, worktree, JSON snapshot and raw output; output is not acceptance evidence.

## Git, gates, scope and test proof

Worktree is `.symphony/worktrees/<issue>`, branch `baton/<slug>-<issue>`, created from HEAD, reused on retry and path-confined under `.symphony` ([workspace L51–98](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/workspace.py#L51-L98)); cleanup force-removes it then fallback `rmtree` ([L100–117](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/symphony/workspace.py#L100-L117)). Hooks are the only executable gates. No native test/CI/review/browser acceptance, file allowlist, diff budget, token/USD budget or merge action. Tests prove claimed dispatch/reconcile ([tests](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/tests/test_orchestrator.py#L42-L76)), state retry ([state tests](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/tests/test_state.py#L15-L75)) and worktree lifecycle ([workspace tests](https://github.com/mraza007/baton/blob/7bb5fb73c08f31d897b7b64e85b3247a0292eebd/tests/test_workspace.py#L40-L84)), not e2e PR/CI/resume.

## WMS verdict

Adapt explicit retry/reconcile/worktree mechanics. Reject as-is: PR-exists equals success, unbounded outer retry, no resume, scoped contract or independent acceptance.

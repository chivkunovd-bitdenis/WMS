# orchestrator-sh — reverse engineering

Pinned commit: [`7fe2c97a6f940179ebfdf5df11ae2d742c33ef3e`](https://github.com/gabrielkoerich/orchestrator-sh/tree/7fe2c97a6f940179ebfdf5df11ae2d742c33ef3e), read 2026-08-24. E1 for shell/YAML persistence, checked-in prompts and tested shell entry points; not E1 for semantic acceptance.

## Components, state and happy path

`scripts/backend.sh` is a yq-backed YAML store. Job creation persists id, title, schedule, type, body, labels, agent, directory and command ([L63–80](https://github.com/gabrielkoerich/orchestrator-sh/blob/7fe2c97a6f940179ebfdf5df11ae2d742c33ef3e/scripts/backend.sh#L63-L80)). Shell scripts/tmux provide execution; prompts are versioned files: [route](https://github.com/gabrielkoerich/orchestrator-sh/blob/7fe2c97a6f940179ebfdf5df11ae2d742c33ef3e/prompts/route.md), [plan](https://github.com/gabrielkoerich/orchestrator-sh/blob/7fe2c97a6f940179ebfdf5df11ae2d742c33ef3e/prompts/plan.md), [agent](https://github.com/gabrielkoerich/orchestrator-sh/blob/7fe2c97a6f940179ebfdf5df11ae2d742c33ef3e/prompts/agent.md), [review](https://github.com/gabrielkoerich/orchestrator-sh/blob/7fe2c97a6f940179ebfdf5df11ae2d742c33ef3e/prompts/review.md). Happy path inferred strictly from executable artifacts: persist job → invoke configured command/agent in directory → scripts expose its result. A canonical terminal task-state enum was not found in the proven source set.

## Failure/retry/Git/controls

The repository has [`retry_task.sh`](https://github.com/gabrielkoerich/orchestrator-sh/blob/7fe2c97a6f940179ebfdf5df11ae2d742c33ef3e/scripts/retry_task.sh) and [`cleanup_worktrees.sh`](https://github.com/gabrielkoerich/orchestrator-sh/blob/7fe2c97a6f940179ebfdf5df11ae2d742c33ef3e/scripts/cleanup_worktrees.sh), plus Bats tests ([`tests/orchestrator.bats`](https://github.com/gabrielkoerich/orchestrator-sh/blob/7fe2c97a6f940179ebfdf5df11ae2d742c33ef3e/tests/orchestrator.bats)). This proves mechanisms exist, not classification, caps, idempotency or resume semantics: those remain unknown until their bodies/tests are traced as a controller graph. No proof was found for browser acceptance, automatic PR merge, allowed-file scope or cost budget.

## WMS verdict

Adapt checked-in prompts and human-readable durable jobs. Reject it as a reference controller: YAML records and retry shell scripts do not provide independently enforced state transitions or completion evidence. The WMS controller should retain only the transparency pattern, not its terminal semantics.

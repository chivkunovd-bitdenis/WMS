# Stringbean

## 1–3. Идентификация, класс, границы

Проверено 2026-08-24, HEAD [`eaa6d20`](https://github.com/ZenulAbidin/stringbean/tree/eaa6d20723db3dfbaf3cdcb19f1aae1010af50e2). E1: Python workflow engine/state/templates/tests. Local resumable multi-provider planning/review/implementation workflow; not itself proof of UI/browser acceptance.

## 4–6. State and transitions

Workflow engine constructs adapters for Codex, Claude, Grok and generic CLI ([workflow L69–74](https://github.com/ZenulAbidin/stringbean/blob/eaa6d20723db3dfbaf3cdcb19f1aae1010af50e2/src/agent_relay/workflow.py#L69-L74)), persists events/calls through `RunEventStore` and `CallStore` during construction ([L116–158](https://github.com/ZenulAbidin/stringbean/blob/eaa6d20723db3dfbaf3cdcb19f1aae1010af50e2/src/agent_relay/workflow.py#L116-L158)). Full named transition graph is intentionally not inferred from imports.

## 7–13. Decisions, prompts, artifacts, recovery, Git, scope, budget

Model mode is deterministically inferred from task language/size with low/medium/high signals ([L84–114](https://github.com/ZenulAbidin/stringbean/blob/eaa6d20723db3dfbaf3cdcb19f1aae1010af50e2/src/agent_relay/workflow.py#L84-L114)); policy wrapper imports show execution-profile, denied command/Git subcommand and environment redaction mechanisms ([L35–65](https://github.com/ZenulAbidin/stringbean/blob/eaa6d20723db3dfbaf3cdcb19f1aae1010af50e2/src/agent_relay/workflow.py#L35-L65)). Checked-in prompts are [orchestrator planning](https://github.com/ZenulAbidin/stringbean/blob/eaa6d20723db3dfbaf3cdcb19f1aae1010af50e2/src/agent_relay/templates/orchestrator-planning.md) and [reviewer](https://github.com/ZenulAbidin/stringbean/blob/eaa6d20723db3dfbaf3cdcb19f1aae1010af50e2/src/agent_relay/templates/reviewer-review.md). State/recovery are covered by [state tests](https://github.com/ZenulAbidin/stringbean/blob/eaa6d20723db3dfbaf3cdcb19f1aae1010af50e2/tests/test_state.py) and [workflow tests](https://github.com/ZenulAbidin/stringbean/blob/eaa6d20723db3dfbaf3cdcb19f1aae1010af50e2/tests/test_workflow.py), but terminal acceptance/browser gate not proven in examined code.

## 14–16. Weaknesses, WMS, verdict

Heuristic mode inference risks treating ambiguous real product work as low mode; it is not a scope contract. Durable call/event artifacts and policy wrappers are valuable. Verdict: **adapt run evidence and deterministic execution policy; reject task-text heuristic as sole routing**.

## 17. Evidence

- [Workflow engine](https://github.com/ZenulAbidin/stringbean/blob/eaa6d20723db3dfbaf3cdcb19f1aae1010af50e2/src/agent_relay/workflow.py#L35-L158)
- [State tests](https://github.com/ZenulAbidin/stringbean/blob/eaa6d20723db3dfbaf3cdcb19f1aae1010af50e2/tests/test_state.py)

# Detent — reverse engineering result

Pinned commit: [`478561dd6b82a8d7d3bfa1aa297ea6b9c4cc5c19`](https://github.com/digitaldrywood/detent/tree/478561dd6b82a8d7d3bfa1aa297ea6b9c4cc5c19), inspected 2026-08-24 through pinned tree/API. E1 for the presence of independently tested subsystems; full controller transition semantics remain unproven because the temporary clone did not finish and no single dispatcher file was recovered line-by-line.

## Proven component map

The pinned tree contains SQL store definitions (`db/queries/store.sql`), board snapshot store, dispatch status, admission, budget/estimate/pricing/override, CI trigger coordinator and shutdown state. This is materially stronger than a README: component-level tests are checked in — [dispatch status](https://github.com/digitaldrywood/detent/blob/478561dd6b82a8d7d3bfa1aa297ea6b9c4cc5c19/internal/store/dispatch_status_test.go), [CI coordinator](https://github.com/digitaldrywood/detent/blob/478561dd6b82a8d7d3bfa1aa297ea6b9c4cc5c19/internal/citrigger/coordinator_test.go), [shutdown state](https://github.com/digitaldrywood/detent/blob/478561dd6b82a8d7d3bfa1aa297ea6b9c4cc5c19/internal/shutdown/state_test.go), and [budget](https://github.com/digitaldrywood/detent/tree/478561dd6b82a8d7d3bfa1aa297ea6b9c4cc5c19/internal/budget). It also ships workflow templates, e.g. [GitHub-local YAML](https://github.com/digitaldrywood/detent/blob/478561dd6b82a8d7d3bfa1aa297ea6b9c4cc5c19/docs/templates/detent.github_local.yaml).

## What is and is not established

The evidence establishes persisted store + board-oriented orchestration + first-class CI/budget/shutdown test surfaces. It does **not** establish exact state enum, transition predicates, retry cap/resume protocol, prompt contents, Git worktree/PR merge rules, scope allow-list, browser acceptance or what terminal state means. Those claims are intentionally unknown; the earlier card's implication that this is a full code-complete pipeline was not justified.

## WMS verdict

Keep Detent in the research set as a candidate for a further source pass because budget/admission/shutdown are real tested modules. Do not transfer any control-flow design from it yet. The only safe current lesson is architectural: budget and shutdown should be code-owned state with tests, not prose in an agent prompt. This is a **defer/research-further** verdict, not adoption.

## Evidence

- [budget tests](https://github.com/digitaldrywood/detent/tree/478561dd6b82a8d7d3bfa1aa297ea6b9c4cc5c19/internal/budget)
- [workflow overlays](https://github.com/digitaldrywood/detent/blob/478561dd6b82a8d7d3bfa1aa297ea6b9c4cc5c19/docs/workflow-overlays.md)
- [merge train documentation](https://github.com/digitaldrywood/detent/blob/478561dd6b82a8d7d3bfa1aa297ea6b9c4cc5c19/docs/merge-train.md)

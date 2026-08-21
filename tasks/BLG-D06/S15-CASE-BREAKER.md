# S15 independent case-breaker - BLG-D06

## Verdict

`CASE_BREAKER_PASSED`

This review is limited to the fixed S15 package for `BLG-D06-C1`. The reviewer
did not author the cases and did not modify `S15-CASES.json` or
`S15-CASE-FACTORY.md`. This result confirms that the four breaker
specifications attempt to falsify the approved behavior through distinct,
locally executable attack lanes. It is not a case audit, controller receipt,
S16 approval, Dev authorization, release action, or evidence of test execution.

## Reviewed package

- `S15-CASES.json`:
  `sha256:a56a63ff9cf75b4ca35cd1c75f0a3ed8b7d145d221f5b7e1a8b8aaa415533cd9`
- `S15-CASE-FACTORY.md`:
  `sha256:c38ce92c83eabcac5af9792ea3f94d9db7cbb0bf3a310ed6bd8a80429347bae5`
- Accepted inputs: S09 `UX_CONTRACT_READY`, S10 `DESIGN_APPROVED`, S11
  `PRODUCT_CONTRACT_APPROVED`, and S12 `TASK_CUT_READY` from the current
  `state.json` snapshot.
- Baseline/package commit:
  `182e5d22cdf9b86355cd834143b70fcccf4e7067`.

## Breaker attack results

### `D06-C1-B01`: persisted state and stale selection

This lane attacks the safe default through hostile URL/history/storage state
and a stale selected `OLD/` row. A fresh context is required per injected
variant. Opening and reloading the route must neutralize the archive scope,
show only current rows, and remove any hidden archive from the adjacent detail
context. This directly attempts to falsify default hiding, non-persistence, and
selection cleanup rather than repeating the ordinary first-open case.

### `D06-C1-B02`: search bypass

This lane parameterizes exact, partial, and case variants independently across
SKU, name, seller, and WB vendor code. The same archive-only token is compared
under `active` and explicit `all` scopes. It therefore attacks the ordering of
the archive predicate and local search predicate: search must not bypass the
current-only default, while the explicit archive choice must reveal the same
fixture row and its archive identity.

### `D06-C1-B03`: classifier and responsive cue loss

This lane combines exact `OLD/` membership with lower-case, non-initial, and
non-SKU near matches, long values, 250 rows, and a 360 x 640 viewport. It
switches among `all`, `archived`, and `active` after the safe initial render.
The attack can expose false archive classification, a clipped literal SKU,
loss of the neutral `Архив` cue, dropped columns, or unusable horizontal
inspection. It covers explicit archive filtering and long/narrow behavior with
a materially different adversarial fixture from the default-list lane.

### `D06-C1-B04`: stale fallback and API/data side effects

This lane surrounds scope and search changes with delayed and rejected existing
catalog reads after a successful mixed response. Instrumentation records every
method, URL, query, and body, while mutation, worker, and external routes are
tripwires. It attempts to falsify the approved local-only boundary by detecting
stale unfiltered fallback, a new archive/search request contract, any write or
selection side effect, fixture mutation, queue work, or WB/Ozon call.

## Direct-case specifiability

The eight direct cases are task-specific and sufficiently specified for S19:

- `D06-C1-01` proves current-only first open, route return, and reload.
- `D06-C1-02` proves archive-only searches cannot override `active`.
- `D06-C1-03` proves the exact `all`/`archived`/`active` journey, counter, literal
  SKU, chip, and hint.
- `D06-C1-04` proves logical AND composition and hidden-selection cleanup.
- `D06-C1-05` names each loading, empty, archive-only, no-match, and failed-read
  visible result.
- `D06-C1-06` fixes the 250-row fixture, 360 x 640 viewport, long values,
  tooltips, four columns, and local scroll assertions.
- `D06-C1-07` records unchanged reads and fails on API, write, worker, data, or
  external-boundary drift.
- `D06-C1-08` distinguishes the exact case-sensitive initial `OLD/` SKU prefix
  from lower-case, missing-slash, non-initial, and non-SKU near matches.

Every case names a deterministic local fixture/reset contract, actor, route,
steps, timeout, planned Playwright reference, expected visible/read boundary,
read-back, reload assertion, and accepted oracle. Coverage references resolve
to unique case IDs, all four breaker lanes are distinct, and
`python3 scripts/pipeline/run.py validate --task-id BLG-D06` passes. No live
service, marketplace, database, worker, credential, or production access is
needed to bind or execute these specifications.

## Exact next action

Dispatch a distinct `case-auditor` to verify the complete S15 coverage matrix,
fixture isolation, planned S19 bindings, this breaker confirmation, and the two
exact package hashes above. The case-auditor, not this breaker, decides
`CASE_AUDIT_PASSED` or returns the package to BA repair. No minimum closure
artifact is required from BA for this breaker verdict.

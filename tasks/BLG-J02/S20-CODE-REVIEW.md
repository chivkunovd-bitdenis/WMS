# S20 CODE_REVIEW - BLG-J02

Role: `pipeline-reviewer`

Agent: `codex-pipeline-reviewer-blg-j02-s20`

Verdict: `CODE_REVIEW_REWORK`

## Scope and independence

This review covers implementation commit
`fba101e0cf8241ae1f5eab7a9cdbb4819c27e8e4` and automation commit
`3405976758196a8627279a2b98e062d3f9287a5f` against the accepted S09-S19
artifacts. The reviewer did not produce either commit and did not change the
implementation, tests, case oracles, release state, production state, external
systems, credentials, or secrets.

## Findings

### 1. AUTOMATION - required GOLD cases do not have runnable bindings

`S19-TEST-AUTOMATION.md` declares all seven cases executable, but the added
tests implement only selected-portal expiry/isolation and one fulfillment
return path. There is no runnable test for the unsafe-target matrix
`J02-C1-03`, the ordinary-error matrix `J02-C1-04`, repeated submit/failed
login/repeated expiry/one-time consumption `J02-C1-05`, no-replay sentinels
`J02-C1-06`, or the `360 x 640` overflow and button-bounds matrix
`J02-C1-07`. The S19 row for `J02-C1-03` and `J02-C1-06` names only a fixture
boundary, not an `executable_ref/test_id`.

This violates the S19 gate: every deterministic GOLD case must have a runnable
reference before S20 can pass. The full two-spec run contains five tests, of
which four exercise new J02 behavior; green execution does not cover the
missing matrices.

Minimum closure: bind every `J02-C1-01` through `J02-C1-07` case to explicit
Playwright test IDs, implement the missing parameterized variants and request/
navigation/viewport assertions, then run the complete unfiltered J02 suite.

### 2. IMPLEMENTATION - recovery readiness is never consumed

`useAuth` sets `sessionRecoveryReady` to `true` after the fresh profile but
never resets it. Both portal effects depend on `pendingAuthReturn`, clear that
state, and navigate while readiness remains true. The state change schedules
the effect again with a null target, so `consumeAuthReturnTarget(null, portal)`
navigates to the fallback a second time. A restored route can therefore be
immediately replaced by the fallback; later profile changes can also trigger a
stale recovery navigation.

The existing happy-path test starts on the fulfillment fallback pathname and
asserts the query/hash at an intermediate moment, so it does not prove a
non-fallback route remains restored after the effect settles.

Minimum closure: expose an explicit one-shot recovery consume/reset operation,
atomically consume readiness and the target, and prove a non-fallback route
with query/hash remains stable after settling and after Back/reload.

### 3. IMPLEMENTATION - failed login keeps stale return intent

The login handler clears only the visible `sessionExpired` flag. It does not
clear `recoveringSessionRef`, `sessionRecoveryReady`, or the parent
`pendingAuthReturn`. After a bad-password or network failure, a later
successful login can still mark recovery ready and restore the route captured
before the failed attempt. This contradicts accepted case `J02-C1-05`, which
requires a failed login not to preserve the prior target.

Minimum closure: cancel the recovery transaction and discard the target on
every failed/cancelled/password-setup/role-mismatch branch, with a test that a
later ordinary successful login uses the portal fallback and cannot revive the
old pathname/query/hash.

### 4. IMPLEMENTATION - route allow-list is not role authorization

`captureAuthReturnTarget` accepts broad fulfillment prefixes before the fresh
profile is known. After login, `App` checks only `isFfPortalRole(me.role)`, and
`consumeAuthReturnTarget` checks only the stored portal value. It never checks
the target against the fresh role and `me.permissions`. A staff user can be
returned to a recognized but unavailable route such as FBS, packaging,
settings, inventory, or shift-lead pages; some routes render an access-denied
placeholder instead of the contract-required silent fallback.

Minimum closure: validate the exact target against the fresh role and
permissions before navigation. Add staff-role breakers for restricted routes
and assert the fulfillment fallback without disclosure of the rejected route
or permission.

### 5. IMPLEMENTATION - arbitrary query/hash data is retained without the approved data filter

The target helper concatenates `search` and `hash` verbatim. The approved
contract permits route context but explicitly forbids retaining token,
password, request-payload or API-error data. A recognized route containing
sensitive query/hash keys is currently stored and restored unchanged.

Minimum closure: define and enforce an allow-list or redaction rule for query
and hash data, reject sensitive return targets, and add token/password/error
payload breaker variants that prove no secret-like value is retained, rendered,
or restored.

## Positive evidence

- Structured `401` plus exact `detail: "invalid_token"` is classified at the
  `/auth/me` boundary rather than globally.
- The selected portal token is cleared through the existing portal-specific
  storage key, and the added isolation test preserves the other portal token.
- The approved Russian message uses the existing `ErrorNotice`; the reviewed
  diff does not expose a raw token value, add backend/database/worker changes,
  or introduce live marketplace calls.
- The two reviewed commits contain no unrelated production, release, secret,
  or marketplace-operation changes.

## Verification

- `python3 scripts/pipeline/run.py next --task-id BLG-J02` - `RUNNING/S20`,
  role `pipeline-reviewer`, no blocker.
- `python3 scripts/pipeline/run.py validate --task-id BLG-J02` - passed before
  the review verdict.
- `npm run build` in `frontend/` - passed; only the existing large-chunk warning.
- Targeted ESLint for the five implementation files and two test files - zero
  errors, one pre-existing `react-hooks/exhaustive-deps` warning in `App.tsx`.
- Full unfiltered two-spec Chromium run - `5 passed`; coverage inspection found
  the missing GOLD bindings listed above.
- `git diff --check` - required before handoff.

## Controller handoff

The immediate owning failure is `AUTOMATION`, routed to S19 through controller
finding `REQUIRED_CASE_WITHOUT_BINDING`. S19 must first create the missing
runnable bindings without changing any oracle. If those GOLD cases expose the
implementation defects above, the controller must route the red implementation
work to S18 before a new independent S20 review. No owner input, production
access, release action, live WB/Ozon call, or secret operation is required.

## Post-verdict controller incident

The required `failure --finding REQUIRED_CASE_WITHOUT_BINDING` transition put
the task into `WAITING/S19`, but the controller's generic invalidation cleared
all accepted S01-S19 verdict records instead of invalidating S19 and downstream
only. The resulting packet reports `done_stages: []` even though the receipt
files and pre-failure state recorded valid S01-S19 history. A plain `resume`
would therefore attempt to replay S01 and is not a safe recovery.

The task is held with reason `CONTROLLER_FAILURE_INVALIDATION_BUG`. Minimum
orchestration closure is to repair/replay the controller journal so the
pre-failure S01-S18 verdict chain is restored, S19 is the first missing stage,
and validation passes without hand-editing `state.json` or receipts. Only then
may the S19 automation repair continue.

# S10 DESIGN_REVIEW - BLG-J02

Role: `pipeline-product`
Agent: `codex-pipeline-product-blg-j02-s10`
Verdict: `DESIGN_REWORK`
Return stage: `S09 UX_CONTRACT_AND_MOCKUPS`

## Decision

The core operator outcome is correct: replace `invalid_token` with a session
message, keep login as the only next action, and restore only a safe route in
the same portal. The proposed design cannot be approved yet because its fallback
state gives a successful login the visual semantics of an error and its ui-kit
mapping silently expands the scope beyond the new visible zone.

## Blocking findings

1. `S09-UX-CONTRACT.md:36,99-108` requires `ErrorNotice` for the successful-login
   fallback message `Вход выполнен. Открыт доступный рабочий экран.` The actual
   ui-kit component is always `Alert severity="error"`. This violates UX canon
   R-16 and R-23: red/error treatment means work is blocked or failed, while the
   contract explicitly says authentication succeeded and an accessible screen
   was opened. The warehouse operator would receive two contradictory signals.

2. `S09-UX-CONTRACT.md:33-35,40-42` says the existing login frame and form use
   `ScreenShell`, `ScreenHeader`, `TextInput`, and `PrimaryAction`. The current
   `PublicAuthScreen` uses its established raw MUI composition. BLG-J02 adds a
   session notice and safe return behavior; it does not carry a rationale or
   scope for redesigning the entire public authentication screen. Under canon
   R-37, the contract must identify the new notice as the changed ui-kit zone
   and explicitly preserve the untouched legacy form, or separately declare a
   real design-system/scope dependency.

3. The textual trees do not provide a reviewable narrow-viewport composition.
   The contract itself requires S10 to prove that the notice does not push the
   login command below the usable warehouse viewport (`S09-UX-CONTRACT.md:138-143`),
   but supplies no viewport, spacing, overflow, or long/error-state mockup from
   which that can be judged. Pipeline S10 requires overflow and long-data review,
   so this assertion needs a concrete mockup for both fulfillment and seller
   login variants.

## Minimum closure for S09

- Use an error treatment only for the expired-session condition.
- For successful safe fallback, remove the extra notice if the ordinary start
  screen is self-explanatory, or use an existing non-error canonical treatment.
  If none exists and the feedback is required, declare `DESIGN_SYSTEM_GAP`
  instead of reusing `ErrorNotice`.
- Limit ui-kit migration claims to the new visible zone unless a separate
  approved scope explicitly requires conversion of the legacy auth screen.
- Add a concrete narrow-viewport mockup covering the session notice, login busy
  state, existing login error, and safe fallback for both portals.

No implementation, tests, secrets, deployment, or external systems were touched.

## Controller handoff note

The controller accepted `PRODUCT_REJECTED` with `resume_stage: S09`, and the
task snapshot records `current_stage: S09`. However, the subsequent `next`
command reports `S01` because the failure route invalidated S01, S02, and S09
together. No dispatch was generated: a controller owner must reconcile this
S09-versus-S01 routing inconsistency before another worker is assigned.

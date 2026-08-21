# S14 ARCHITECT_FALSIFICATION - BLG-D12

## Binding

- Task: `BLG-D12`
- Card: `BLG-D12-C1`
- Stage: `S14 ARCHITECT_FALSIFICATION`
- Role: `pipeline-reviewer`
- Agent: `codex-pipeline-reviewer-blg-d12-s14`
- Reviewed baseline: `69c271678782d7dcfa39df97cd905cbee1678727`
- Reviewed plan: `tasks/BLG-D12/S13-ARCHITECT-PLAN.md`
- Dependency inspected after the independent plan: `tasks/BLG-D09/S13-ARCHITECT-PLAN.md`

## Verdict

`ARCH_REVIEW_PASSED` with arbiter decision `ACCEPT_PLAN_1`.

The S13 plan survives independent falsification. It assigns the effective
frontend cache policy to Caddy, classifies the representation after SPA
resolution, makes the static asset namespace fail closed, requires retained
content-addressed assets, and binds integration proof to the D09 exact-artifact
identity chain. No unresolved high-risk architecture conflict permits a return
to S13 at this stage.

## Independent plan built before reading S13

The independent design used four boundaries:

1. Caddy is the sole `Cache-Control` owner for static frontend responses. The
   policy is applied after `try_files` resolves the actual representation, so
   `/`, explicit HTML and client-route fallbacks cannot diverge.
2. `/assets/*` is handled before SPA fallback. Missing assets stay `404`.
   Long-lived immutable caching is allowed only for content-addressed files
   whose URL-to-bytes mapping is proven by the candidate inventory.
3. The candidate identity includes entry-document digests, the complete static
   asset inventory and the active serving configuration. A same-path/different-
   bytes collision fails before promotion.
4. A two-candidate, same-origin fixture proves stale-validator behavior,
   previous-asset retention and an ordinary warm-cache navigation from A to B.
   A cold profile, disabled cache, cache clearing or hard reload cannot satisfy
   the primary browser case.

S13 independently reached the same structure and added useful scope locks,
active Caddy entrypoints, compression-neutral digest checks, and the explicit
D09 dependency.

## Falsification results

| Attack lane | Result | Required downstream enforcement |
| --- | --- | --- |
| `/`, `/index.html`, FF fallback, `/seller/`, seller fallback or slash aliases receive different headers | Survives | S15 must exercise every alias present in the production image for both `GET` and `HEAD`; policy is assigned after static resolution. |
| Caddy directive sorting applies headers before `try_files` rewrite | Survives | Use an explicitly ordered route and validate the adapted Caddy config plus effective responses. |
| Outer ingress appends or replaces `Cache-Control` | Survives | Candidate and later release proof inspect the effective public-origin header and reject duplicate or contradictory values. |
| A non-hashed file under `/assets/` receives `immutable` | Survives with fail-closed interpretation | Filename shape is not sufficient proof. The verifier must cover the complete build inventory, including transitive chunks, CSS imports, fonts and images, and must reject any immutable response absent from that inventory. |
| A hashed-looking missing URL becomes `200 index.html` | Survives | `/assets/*` is isolated from SPA fallback; missing files remain distinct `404` evidence. |
| A content-addressed URL is reused for different bytes | Survives | Candidate assembly and verification fail on any URL collision with unequal digests. |
| Validator from candidate A produces an invalid `304` for changed candidate B HTML | Survives | S15 sends stale and current validators; changed bytes must return B, while `304` is allowed only for byte-identical content. |
| Candidate B removes A assets inside the rollback window | Survives, dependent on D09 interface | Candidate B must include or otherwise serve the retained A inventory at the same origin, with source artifact digest and collision proof. Header checks alone cannot pass. |
| Browser proof secretly uses cold cache, disabled cache, clear-storage, hard reload or a different origin | Survives | Use one persistent profile and stable origin, record A before promotion, then ordinary open/reload to B. Hard reload is supporting evidence only. |
| SHA, web-image digest, entry digest, asset digest and visible build identity come from different candidates | Survives | One D09 manifest identity must bind every recorded value; any mismatch fails S23. |

## Accepted plan constraints

These constraints are fail-closed readings of A2-A4, not optional follow-up
work:

- `asset inventory` means every generated or retained static asset served with
  immutable caching, not only the direct JS/CSS URLs found in entry HTML;
- the effective Caddy configuration must be candidate-bound. In the host-port
  path, `deploy/Caddyfile.http` currently overrides the file inside the web
  image, so its exact bytes must either move into the immutable web artifact or
  be represented by a separately digested release-controller artifact in the
  D09 manifest;
- the D09/D12 interface must provide the current and previous web-artifact
  identities, complete asset URL/digest inventories, a deterministic way to
  obtain retained bytes, the retention window, and collision rejection;
- if D09's accepted implementation interface omits any of those fields, the
  retention lane must return to S13 before widening scope. S23 remains blocked
  until the interface exists and the two-candidate proof passes;
- no config-only success may claim rollback retention, exact-artifact browser
  identity or production readiness.

## Scope and safety judgement

The accepted plan remains one atomic release card. It changes no warehouse
workflow, API, database, worker, authentication, tenant or marketplace
behavior. This stage performed no implementation, build, test execution,
commit, push, release, deployment, production request, browser acceptance,
secret access or live WB/Ozon action.

## Handoff

Next stage: `S15 CASE_FACTORY`, owned by `pipeline-ba`.

S15 must preserve `BLG-D12-AC01` through `BLG-D12-AC07` and turn every attack
lane above into deterministic direct and breaker cases. The stage must not
weaken the complete-inventory, candidate-bound-config, retained-assets or
ordinary warm-cache requirements.

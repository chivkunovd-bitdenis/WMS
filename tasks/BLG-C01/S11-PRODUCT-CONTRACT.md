# S11 PRODUCT_CONTRACT_APPROVAL - BLG-C01

## Product decision

The warehouse outcome is approved: FBS packing is a tenant-level process
requirement, not an unconditional delivery gate. A tenant whose approved
configuration says that packing is not required must be able to continue the
FBS supply journey without creating or manually completing a packing task.
Tenants that require packing must keep the existing packing gate unchanged.

The approved control is `tenants.fbs_packing_required`. Its safe default is
`true`. Only an explicit value of `false` for the specifically authorized
tenant may select the no-packing journey. A missing, unreadable or unknown
value must fail closed to packing required; it must never disable packing
globally or by inference from an absent task.

## Operator journey and warehouse rationale

1. The operator starts or continues an FBS supply under the existing role,
   tenant, seller and warehouse context.
2. When that tenant has `fbs_packing_required = false`, WMS automatically marks
   the packing stage as not required and lets the supply continue to its
   existing next applicable step. The operator does not create a synthetic
   packing task, press a fake completion action or ask for a production data
   correction.
3. The supply remains traceable: the persisted state and subsequent read-back
   must distinguish an approved automatic no-packing path from a completed
   physical packing task and from an error or missing task.
4. When `fbs_packing_required` is `true` or cannot be resolved safely, the
   existing required-packing journey and its blockers remain in force.

This removes an artificial stop for tenants whose physical process does not
include mandatory packing while preserving the safety gate for tenants whose
process does. Optional packing must not weaken order, marking, cargo-place,
delivery, tenant-isolation or marketplace requirements that are independent
of the packing stage.

## Approved behavioral boundaries

- The setting is tenant-scoped. Seller or warehouse context must not cause one
  tenant's decision to affect another tenant.
- The additive database migration must preserve existing tenants as packing
  required. No existing tenant may become optional merely because the
  migration was applied.
- `false` authorizes only automatic passage of the packing stage. It does not
  authorize skipping picking, marking, cargo-place, delivery preflight,
  marketplace or other independently required checks.
- Repeated processing, worker retry or page reload must keep the same result
  without creating duplicate packing tasks or contradictory state.
- A configuration, migration or runtime failure must be visible as a safe
  operational failure; it must not silently turn required packing into
  optional packing.
- Switching a tenant back to `true` affects subsequent eligibility decisions
  and must not rewrite historical audit truth about supplies already processed.
- Existing required-packing tenants must show no operator-flow regression.

## Required downstream proof

S12 may cut the release work into the smallest vertical cards needed for the
immutable candidate, migration/configuration operation and verification, but
must not merge those authorization boundaries. S13-S15 must cover the additive
migration, fail-closed default, tenant isolation, retry/idempotency, read-back,
reload, required-packing regression and no-packing happy journey. S23 must bind
the full candidate SHA to immutable artifact digests.

Before release authorization, S26 must identify:

- the full immutable 40-character `release_candidate_sha` and artifact manifest;
- the additive migration order and compatibility evidence;
- the exact target tenant and the separately authorized configuration change;
- smoke, stop and rollback procedures that preserve data truth;
- the live post-release operator journey and monitoring denominator/effects.

The historical branch `fix/packing-optional-20260819` and short commit pointer
`f05207c` are discovery evidence only. They are not an approved release SHA and
must not be promoted from this S11 artifact.

## Exact-SHA owner approval stopper

This card and this Product verdict do not authorize deploy, migration against a
live database, tenant configuration mutation or production verification.
S27 is blocked until a separate owner approval names the exact full
`release_candidate_sha`, immutable artifact manifest and target tenant. S28 may
start only after S27 proves that the deployed runtime and artifacts match that
same approved SHA and manifest. Without that approval and exact-artifact proof,
the honest terminal release result is `READY_FOR_RELEASE`, not deploy or `DONE`.

## Out of scope

No code implementation, branch selection, merge, commit, push, secret access,
live deployment, production migration, production data change, live WB/Ozon
operation or Product Browser acceptance is performed or approved at S11.

## Verdict

`PRODUCT_CONTRACT_APPROVED`: the tenant-scoped, fail-closed contract removes
only the packing gate that the tenant's approved warehouse process does not
require, preserves required-packing and all independent safety gates, and keeps
exact-SHA release authorization as a mandatory later owner decision.

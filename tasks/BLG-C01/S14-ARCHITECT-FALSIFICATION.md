# S14 ARCHITECT_FALSIFICATION - BLG-C01

## Verdict

`ARCH_REVIEW_PASSED`

The S13 plan survives falsification only as a plan for a fresh canonical
implementation and immutable release candidate. It does not authorize reuse,
merge or promotion of the discovery branch or its commit.

## Independent checks and observed facts

- The discovery commit is
  `f05207c605ddce9ae7029e8cba6ff902e2d6f1f1`. It changes the tenant flag,
  tenant lookup, box-assignment behavior and tests, but it records automatic
  bypass only by setting `pack_status = packed` and `packed_at`. It does not
  preserve a durable reason that distinguishes bypass from physical packing.
- `origin/etalon...f05207c605ddce9ae7029e8cba6ff902e2d6f1f1`
  has commits on both sides (`21` canonical-only and `4` discovery-only at
  review time). The old commit is therefore discovery evidence, not a release
  candidate.
- The discovery migration revises `20260816_0091`, while `alembic heads` on the
  reviewed canonical worktree reports `20260811_0078`. The discovery migration
  cannot be promoted or copied with its old parent. S17 must capture the actual
  head again and S18 must create a fresh additive revision from that head.
- The existing assignment service scopes box, supply, order and assignment
  reads by `tenant_id`, but concurrent assignment currently has no explicit
  row-locking contract. The new bypass transition must make that concurrency
  contract explicit rather than relying on sequential tests.

## Falsification judgement

### Exact-SHA stopper and old candidate

The plan passes this attack. S23 is the only allowed source of a candidate: it
must integrate the scoped implementation on the controller-allocated canonical
base, build once, and bind the full 40-character Git SHA and tree to immutable
backend, migration, worker and frontend digests. Cherry-picking, merging or
promoting the old branch as a release artifact is forbidden. A rebuild, merge
or rebase creates a new candidate and invalidates downstream proof.

S26 may prepare the packet, but without a separate owner decision naming that
exact S23 SHA, the immutable manifest and one full tenant identifier its only
honest release result is `READY_FOR_RELEASE`. S27 must reject a branch name,
short SHA, the discovery SHA, green tests, or approval of this plan as release
authorization. S28 remains impossible until S27 proves runtime SHA and every
promoted digest equal the owner-approved manifest.

### Additive migration and rollback

The accepted plan is schema-additive:

1. create a new revision from the S17-recorded current head, with no second
   Alembic head;
2. add `tenants.fbs_packing_required` as non-null with database and ORM defaults
   of `true`;
3. add a nullable durable bypass-reason field on the existing FBS order record,
   with no destructive backfill;
4. prove old-application/new-schema compatibility before application promotion;
5. preserve both columns and historical bypass truth during application
   rollback rather than running a destructive downgrade.

Existing tenant rows therefore remain packing-required, existing packed rows
remain historical/physical by a null bypass reason, and existing pending rows
remain pending. Migration or schema-read failure must fail closed and cannot be
interpreted as `false`.

### Tenant-scoped compare-and-set

The words "compare-and-set" in S13 are accepted only with the following atomic
meaning. The release operation must execute one conditional mutation equivalent
to:

```sql
UPDATE tenants
SET fbs_packing_required = false
WHERE id = :owner_authorized_tenant_id
  AND fbs_packing_required IS TRUE
RETURNING id, fbs_packing_required;
```

The affected-row count must be exactly one. A prior read followed by an
unconditional update is not compare-and-set and must be rejected at S20/S26.
The operation may not target by tenant name, seller, warehouse, wildcard or
default. Immediate read-back must prove the same tenant is `false` and a named
control tenant remains `true`; retry must be idempotent and must never broaden
scope. Missing identity, zero or multiple affected rows, ambiguity or failed
read-back is a release blocker.

### Runtime transaction, isolation and audit

Eligibility resolution, automatic bypass audit and box assignment must commit
as one tenant-scoped transaction. The implementation plan must lock or use an
equivalent conditional-write strategy for the selected order rows so two
concurrent requests cannot create contradictory bypass/assignment outcomes.
Every order and box predicate must retain `tenant_id` and `supply_id`; a tenant
flag must be loaded by the authenticated tenant UUID and missing/unreadable
state must fail closed.

The durable truth is:

- `pending` with null bypass reason: not packed and not bypassed;
- `packed` with null bypass reason: physical or historical packing;
- `packed` with reason `tenant_optional`: automatic bypass under the explicit
  tenant decision.

The reason and timestamp must survive commit, API read-back and workspace
reload. Retry must not overwrite the first transition or create a duplicate box
link. The release-controller configuration mutation must additionally leave a
sanitized audit record with actor, timestamp, exact candidate SHA, target tenant
identifier and before/after values; secrets or credentials do not belong in Git
evidence. Restoring the tenant flag to `true` affects future eligibility only
and must not rewrite historical order audit.

### Independent gates and release order

Optional packing suppresses only the packing prerequisite. Picking, marking,
cargo-place, delivery preflight, marketplace and authorization checks remain
independent gates. The accepted release order is additive schema upgrade,
promotion of the already-built immutable application artifact, runtime
SHA/digest verification, then the atomic tenant compare-and-set. No tenant
mutation may occur before exact runtime verification.

Rollback stops qualifying operations, restores the one target tenant to
`fbs_packing_required = true` with an equally scoped conditional mutation,
returns the application to the previously verified artifact, preserves the
additive schema and audit history, and opens the owning-stage incident/rework.

## Mandatory downstream proof

S15 and later technical stages must include destructive cases for migration
head mismatch, pre-existing tenant defaults, missing tenant/configuration,
cross-tenant access, two concurrent assignments, repeat/retry, configuration
flip back to `true`, read-back/reload, required-packing regression, independent
warehouse gates, zero/multiple compare-and-set rows, runtime SHA mismatch and
artifact digest mismatch. S20 must reject any straight promotion of the old
commit, read-then-unconditional tenant update, missing durable bypass reason,
destructive rollback or tenant selector broader than one UUID.

## Blockers and scope

There is no S14 blocker. The exact target tenant and final candidate SHA are
intentionally unknown until S26/S23 respectively and are mandatory inputs to a
future separate owner authorization. This review performs no implementation,
commit, push, merge, migration, configuration mutation, deployment, production
verification or live WB/Ozon operation.

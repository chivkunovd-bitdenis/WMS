# S13 ARCHITECT_PLAN - BLG-C01

## Verdict

`ARCH_PLAN_READY`

BLG-C01 remains one atomic high-risk release card. The old branch is useful as
discovery input, but it is not a releasable artifact. Development must port the
smallest approved behavior onto the controller-allocated canonical base, close
the audit gap described below, and let S23 produce a new immutable candidate.

## Inputs and observed candidate

- Approved Product contract: `tasks/BLG-C01/S11-PRODUCT-CONTRACT.md`.
- Approved atomic cut: `tasks/BLG-C01/S12-TASK-CUT.md`.
- Discovery commit only:
  `f05207c605ddce9ae7029e8cba6ff902e2d6f1f1` on
  `fix/packing-optional-20260819`.
- The discovery commit changes one additive tenant migration, the tenant model,
  tenant settings lookup, box assignment behavior, and backend tests.
- At S13 observation time, the discovery commit is not based on the current
  canonical tip: `origin/etalon...f05207c...` has commits on both sides. Its
  migration revision and full tree therefore cannot be promoted or assumed to
  merge cleanly.
- The discovery implementation sets `pack_status = packed` and `packed_at` for
  the bypass path but stores no durable reason. That conflicts with S11, which
  requires read-back to distinguish physical packing from an approved automatic
  no-packing decision. S18 must close this gap; S20 must reject a straight
  promotion of the discovery commit.

None of these observed SHAs is an owner-approved release SHA.

## Resource graph and locks

### Write set for the future S18 card

The Atomic Dev workspace must take one exclusive lock covering this full set.
The exact migration filename is allocated only after the workspace baseline and
current Alembic head are known.

| Resource | Planned responsibility |
| --- | --- |
| `backend/alembic/versions/<new_revision>_tenant_fbs_packing_required.py` | Add the fail-closed tenant flag and the minimal durable packing-bypass audit field from the actual integration migration head. |
| `backend/app/models/tenant.py` | Map `fbs_packing_required`, non-null with safe default `true`. |
| `backend/app/models/fbs_order.py` | Map the durable bypass reason used to distinguish automatic no-packing from physical packing. |
| `backend/app/services/tenant_settings_service.py` | Read the tenant-scoped flag; missing tenant or unreadable state remains an error, never `false`. |
| `backend/app/services/fbs_packing_box_service.py` | Resolve packing eligibility inside the assignment transaction, persist the bypass audit reason, and keep retries idempotent. |
| `backend/app/api/fbs_orders.py` and/or the existing FBS read model | Expose the persisted bypass reason in read-back without introducing a new operator action. |
| `backend/app/services/fbs_worklist_service.py` | Carry the read-back field if this is the selected existing consumer surface. |
| `backend/tests/test_fbs_packing_box.py` | Direct behavior, retry, required-packing regression, independent-gate and tenant-isolation tests. |
| `backend/tests/test_tenant_settings.py` | Fail-closed setting lookup and default/read-back coverage if the existing fixture layer requires it. |
| Migration/integration tests selected by S15 | Upgrade compatibility, default preservation, audit persistence and application rollback compatibility. |

The read-back contract should use a nullable reason such as
`packing_bypass_reason = "tenant_optional"`. The existing state then remains
unambiguous without rewriting history:

- `pack_status = pending`: packing has not been completed or bypassed;
- `pack_status = packed` and bypass reason is null: physical or historical
  packing completion;
- `pack_status = packed` and bypass reason is `tenant_optional`: automatic
  passage under the tenant-approved optional-packing rule.

S14 may rename this field, but it must preserve the three-state truth and the
additive/no-backfill property. Merely marking an order `packed` is not an
acceptable substitute.

### Read dependencies, not implementation scope

- `backend/app/api/fbs_supplies.py`: existing authenticated box creation and
  order-assignment routes.
- `backend/app/services/fbs_workspace_service.py`: existing next-step and
  reload behavior.
- `frontend/screens.registry.json`, screen `S-03`, and
  `frontend/src/screens/v2/FfFbsSupplyWorkspace.tsx`: operator acceptance
  surface. No visible frontend change is planned.
- `scripts/deploy/release_manifest.py` and protected deploy/controller paths:
  S23/S26 consume them; BLG-C01 must not modify them.
- Existing order, marking, cargo-place, delivery and marketplace checks remain
  independent gates and are not weakened by this card.

No queue, worker, print template, mobile consumer, secret, WB/Ozon client or
live external account belongs to this write set. Discovery of a required write
outside the set returns to S13 for replan before Dev expands scope.

## Migration boundary

1. S17 records the actual canonical base SHA and current Alembic head. S18
   creates a fresh additive revision from that head. The discovery name
   `20260819_0092` may be reused only if it is still unique and has the correct
   parent; otherwise it must be renumbered. A second head is forbidden.
2. Add `tenants.fbs_packing_required` as `NOT NULL` with database and ORM
   defaults of `true`. Existing and newly created tenants remain packing
   required until a separate, explicit configuration mutation selects one
   tenant.
3. Add the nullable order audit field with no destructive backfill. Existing
   packed rows stay physical/historical by the null convention; existing
   pending rows stay pending.
4. Prove old-application/new-schema compatibility before promotion. The safe
   production order is additive schema upgrade first, then exact immutable
   application promotion, then runtime version verification, then the
   tenant-scoped configuration change.
5. A failed application promotion rolls the application back to the prior
   artifact while leaving the additive columns in place. Production rollback
   must not run the destructive Alembic downgrade or erase bypass audit truth.
6. Migration evidence must include current head, planned head, upgrade result,
   defaults for pre-existing tenants, schema/read-back checks, lock/runtime
   observations, and the tested application rollback policy. No live migration
   is authorized by S13.

## Tenant configuration boundary

The schema migration must not contain a tenant ID and must never set the global
default to `false`. BLG-C01 does not add a public UI or general tenant-settings
toggle. Configuration is a separate release-controller operation, parameterized
by the exact owner-authorized tenant.

The S26 packet must specify a compare-and-set operation with these properties:

1. target is one full, unambiguous tenant identifier named by the owner;
2. precondition reads `fbs_packing_required = true` after the exact runtime is
   verified;
3. mutation changes only that row to `false` and records actor, timestamp,
   release candidate SHA and before/after values in sanitized release evidence;
4. immediate read-back proves that the same tenant is `false` and a distinct
   control tenant remains `true`;
5. retry is idempotent and cannot broaden the target set;
6. stop/rollback sets the target back to `true` for subsequent eligibility
   decisions without rewriting historical order audit records.

The operation may use the authorized production control channel selected at
S26, but its credentials and values are never stored in Git evidence. Missing
tenant identity, ambiguous scope, failed compare-and-set or failed read-back is
a release blocker, not a reason to infer `false`.

## Implementation and proof order

1. **S14 - falsification.** Independently challenge the migration parent,
   physical-vs-bypass audit model, concurrency/idempotency, tenant scope,
   rollback and exact-SHA proof.
2. **S15-S16 - cases and Product gate.** Bind direct and breaker cases to the
   approved card before any workspace or code change.
3. **S17-S18 - isolated port and repair.** Reconstruct only the scoped behavior
   on the controller-provided base. Do not merge the old branch wholesale.
4. **S19-S22 - executable proof, review and tests.** Require migration,
   behavior, tenant-isolation, retry, read-back/reload and existing required
   packing regression evidence. No live external marketplace calls are needed.
5. **S23 - immutable candidate.** Integrate the scoped commit, run full required
   regression, and build once. Record the full 40-character integration SHA,
   tree hash, backend artifact digest, migration bundle digest and the declared
   unchanged worker/frontend artifact digests. Any merge, rebase or rebuild
   creates a new candidate and invalidates downstream proof.
6. **S26 - release packet.** Name the exact candidate, immutable manifest,
   migration order, target tenant, configuration compare-and-set, smoke,
   stop/rollback and monitoring plan. Without separate owner approval, S26 must
   end at `READY_FOR_RELEASE`.
7. **S27-S28 - separately authorized release only.** Promote the already-built
   artifact, verify runtime SHA and digests, then perform the approved tenant
   mutation and live trace. These stages are not authorized by this plan.

## Required S15/S22 scenarios

### Optional-packing journey

On an isolated synthetic tenant with the flag explicitly `false`, create or use
an otherwise eligible FBS supply whose order is still packing-pending. Assign
the order to an existing physical box through the existing operator/API path.
Prove all of the following:

- assignment succeeds without creating or completing a synthetic packaging
  task;
- `pack_status` becomes downstream-compatible while the bypass reason is
  exactly `tenant_optional`;
- box assignment, bypass reason and timestamp survive commit, API read-back and
  workspace reload;
- repeating the same action/retry does not duplicate a box link, task or audit
  transition;
- marking, cargo-place, delivery and marketplace blockers still behave as
  independent gates.

### Required-packing regression and isolation

Run the same attempt for a tenant with explicit `true`, a tenant relying on the
safe default, and a separate tenant while only the optional tenant is `false`.
Each unpacked order must remain blocked with `order_not_packed`, with no state or
cross-tenant mutation. A missing tenant/configuration read must fail visibly and
must not pass the gate.

### Configuration-history journey

After one automatic bypass, change the synthetic tenant back to `true`. A new
pending order must require packing, while the previously bypassed order retains
its `tenant_optional` audit reason. This proves configuration changes affect
future eligibility and do not rewrite history.

## Future live operator trace owned by S28

Only after exact-SHA owner approval and successful S27 proof, an authorized
operator may run one bounded scenario on the named tenant and existing approved
FBS surface `S-03`:

1. capture sanitized baseline: runtime SHA/digests, migration head, tenant flag,
   role, supply and order state;
2. place one otherwise eligible packing-pending order into its approved physical
   box without a fake packing action;
3. observe the normal next applicable step;
4. reload and read back box membership plus the automatic bypass audit reason;
5. confirm no synthetic packaging task, duplicate assignment, cross-tenant
   effect or skipped independent gate;
6. count the attempt in the signed monitoring denominator and compare it with
   the expected durable effect.

The trace must not call live WB/Ozon merely to prove this internal gate. If the
selected supply would cause an irreversible marketplace side effect, use a
different owner-approved fixture or stop with a typed release blocker.

## Stop and rollback criteria

Stop before or during release on any migration-head mismatch, missing manifest,
runtime SHA/digest mismatch, target-tenant ambiguity, failed configuration
compare-and-set/read-back, missing bypass audit, duplicate assignment,
cross-tenant effect, required-tenant bypass, skipped independent gate, or
operator journey failure.

Rollback means: stop qualifying operations, restore the target tenant to
`fbs_packing_required = true` for future decisions, roll the application back to
the previously verified artifact, preserve additive columns and historical
bypass evidence, and open the owning-stage rework/incident. It never means
dropping the columns or relabeling automatically bypassed orders as physically
packed.

## Exact-SHA owner approval stopper

**S27 and S28 are forbidden without a separate owner approval that names the
exact full S23 `release_candidate_sha`, its immutable artifact manifest and the
single target tenant.** Approval of BLG-C01, S11, S12, this S13 plan, a branch
name, a short SHA, the discovery commit, green tests or `READY_FOR_RELEASE` does
not satisfy this stopper.

S28 additionally requires S27 evidence that the deployed runtime SHA and every
promoted digest equal that same owner-approved candidate. Until both conditions
exist, no deploy, live migration, tenant mutation, production operator action or
production monitoring may run.

## Non-blocking decisions and remaining owner input

- The target tenant is intentionally not guessed at S13. It becomes mandatory
  in S26 and in the separate exact-SHA approval before S27.
- The final release SHA is intentionally unknown at S13. S23 is its only source
  of truth.
- No secret, production access, external marketplace action, commit, push,
  merge or deploy is needed to continue to S14.

There is therefore no S13 blocker. The plan is ready for independent
falsification.

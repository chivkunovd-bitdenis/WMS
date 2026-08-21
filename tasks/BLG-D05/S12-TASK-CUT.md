# S12 TASK_CUT - BLG-D05

## Verdict

`TASK_CUT_READY`

## Atomic vertical cards

### `BLG-D05-C1` - Fail-closed reconciliation inventory and decision register

**Observable operational result.** An authorized Denmarcs data owner can obtain
a non-mutating, tenant- and seller-scoped inventory of unlinked marking codes.
Every row has a reproducible proposed classification: `CONFIRMED_LINK`,
`REVIEW_REQUIRED`, `SKIPPED_ALREADY_CONSUMED`, or another explicit non-action
reason. The inventory totals reconcile to the source population and a row is
never made allocatable by this card.

**Vertical boundary.** This card contains candidate generation, mandatory
evidence evaluation, stable masked-code reference/fingerprint, source and
candidate references, decision input hash, reason code and append-only
proposed-decision audit. It also provides the reviewable `OLD/` to current-card
lineage mapping surface for the Denmarcs data owner. It is independently useful:
it gives the owner a complete, safe list of what may be applied and what must
remain under review, without mutating stock, ownership, product links or the
marking-code lifecycle.

**Safety rules.** A row is `CONFIRMED_LINK` only when same-tenant,
same-seller, losslessly normalized GTIN equality, explicit approved lineage
where applicable, one current canonical target and existing lifecycle
eligibility all hold. Missing, inconsistent, foreign, stale or non-unique
evidence produces `REVIEW_REQUIRED`; SKU/name/sort order/`OLD/` prefix are not
proof. Foreign identifiers do not reveal their existence. Raw CIS/DataMatrix
and tenant payloads do not enter ordinary logs, Git evidence or reports.

**Acceptance cases for S15.**

| ID | Fixture / oracle | Expected result |
| --- | --- | --- |
| `D05-C1-AC01` | One same-tenant/seller unlinked available code, exact normalized GTIN, one current target and data-owner-approved `OLD/` lineage | Inventory proposes `CONFIRMED_LINK`, with complete masked audit evidence; source totals reconcile and the code remains unchanged/unavailable until C2. |
| `D05-C1-AC02` | Missing, multiple, conflicting or duplicate candidate products; or an `OLD/` relation without an approved lineage record | Each affected row is `REVIEW_REQUIRED` with its explicit reason; no inferred target is emitted. |
| `D05-C1-AC03` | Same GTIN/SKU/barcode/name exists in another tenant or seller | Foreign record is absent from the candidate set and response/evidence does not disclose it; neither tenant changes. |
| `D05-C1-AC04` | Reserved, printed, applied, introduced, transferred, shipped, defective, replaced or void code | Row is explicitly skipped/non-actionable and historical lifecycle/link evidence remains intact. |
| `D05-C1-AC05` | Re-run the same source, then run with changed evidence or source hash | Identical input yields the same decision identity without duplicate audit facts; changed input creates a new proposed decision and invalidates stale approval. |

### `BLG-D05-C2` - Apply approved reconciliation decisions without unsafe use

**Observable operational result.** From a C1 decision register, a controlled
job applies only still-valid, approved `CONFIRMED_LINK` rows. Each such code is
linked to its sole canonical product and can re-enter the existing lifecycle
only if it is otherwise eligible. Every uncertain, stale, failed or
non-actionable row stays durably `REVIEW_REQUIRED` or skipped and is excluded
from allocation, reservation, printing, application, transfer and shipment.
The resulting counts and per-row read-back are visible to controlled data
review, including partial failure.

**Vertical boundary.** This card includes the additive persistence needed for
classification/link decisions and append-only audit, a restartable idempotent
per-code apply unit, mutation-time tenant/seller/ownership/lifecycle recheck,
post-write read-back, and an additive restore rehearsal. It is one card because
a link without allocation exclusion, audit/read-back, retry behavior and
restore evidence would leave an unsafe or non-recoverable warehouse outcome.
It consumes only the C1 decision register and required data-owner approvals.

**Safety rules.** The worker must stop an individual row, not choose a best
candidate, when evidence changes, the code is concurrently reserved/used, the
tenant or seller no longer matches, authorization fails or lifecycle eligibility
changes. A valid row cannot make another row usable. No mutation changes
tenant, seller or code ownership; no update deletes a code, rewrites a
historical event or reuses a consumed code. Reclassification/reassignment is a
new reviewed decision that supersedes, rather than overwrites, history.

**Acceptance cases for S15.**

| ID | Fixture / oracle | Expected result |
| --- | --- | --- |
| `D05-C2-AC01` | C1-approved, still-current same-tenant/seller eligible row with one target | Exactly one link/classification is applied, audit captures before/after and post-write read-back agrees; only this eligible code may return to the existing allocation path. |
| `D05-C2-AC02` | `REVIEW_REQUIRED`, unknown, unreadable, expired or missing-approval decision | No product link or availability is created; row remains durably excluded with a reason. |
| `D05-C2-AC03` | Preview is valid, then target/code ownership, evidence or lifecycle changes before apply; include concurrent reservation/use | Apply stops that row with no stale mutation or consumption; other independent valid rows retain their own result. |
| `D05-C2-AC04` | Mixed batch where one mutation fails, followed by retry and duplicate execution | Each code is atomic and idempotent: successful rows are not duplicated, failed rows are reported and quarantined/skipped, and totals/read-back reconcile. |
| `D05-C2-AC05` | Same identifier supplied by another tenant/seller at apply time | Authorization fails without existence disclosure and without mutation on either side. |
| `D05-C2-AC06` | Applied decision followed by correction/reassignment and restore rehearsal | New append-only decision references the superseded one; restore removes only newly applied reconciliation surface, preserves codes/events after operational use, and leaves unresolved rows retained. |

## Delivery order and ownership boundaries

1. `C1` is first. It defines a reviewable, non-mutating decision population;
   it must not be silently replaced by a bulk repair script or direct database
   update.
2. `C2` depends on a stable C1 decision input plus explicit data-owner approval
   for lineage/manual decisions. It applies no row outside that input.
3. `S13 ARCHITECT_PLAN` owns the resource graph, actual schema and additive
   migration choice, transaction/locking strategy, job invocation and access
   boundary, compatibility/restore design, and the exact file/worktree locks.
   S12 does not select tables, routes, services, queues, migrations or code.
4. The Denmarcs data owner owns source quality and the explicit `OLD/` to
   current-card lineage approval. The data owner does not gain authority to
   cross tenants, bypass lifecycle eligibility or mutate production directly.
5. `S15` translates every acceptance row above into direct and breaker cases,
   with deterministic local fixtures, reset method and planned automation.
   It additionally covers volume/restart, masked evidence, population
   reconciliation, compatibility and negative authorization.
6. `S20` independently reviews that the implementation has no cross-tenant or
   cross-seller candidate/read/mutation path, fails closed, is atomic per code,
   keeps the audit append-only, does not expose raw codes, and preserves
   lifecycle/history/restore guarantees. `S22` and `S23` own the resulting
   functional and integration proof for `tenant_sensitive` and
   `database_change`.

## Explicit exclusions

This cut approves no implementation, migration, direct repair, schema choice,
product merge/deletion, `OLD/` visibility change, operator UI change, commit,
push, deployment, secret access, live Denmarcs/WB/Ozon call, production data
read or production mutation. `BLG-F01` remains a dependency for canonical
block/dependency registry integration; it is not permission to weaken the
no-auto-use rule.

## Handoff

**Next stage:** `S13 ARCHITECT_PLAN`, owned by `solution-architect`, because
the task has the `database_change` trait. The architect receives this task cut,
S11 contract and C1/C2 acceptance matrix. Any change to the two-card boundary
or the fail-closed product contract requires S12 rework before later Product
approval for development.

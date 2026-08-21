# S12 TASK_CUT - BLG-D17

## Verdict

`TASK_CUT_READY`

## Atomic vertical cards

### `BLG-D17-C1` - Fail-closed void reconciliation and unavailable-reason register

**Observable operational result.** An authorized user can run a non-mutating,
tenant- and seller-scoped reconciliation of marking codes that are in `void`
after a binding attempt. Every source row is accounted for exactly once and has
a durable, human-readable unavailable reason or a `RECOVERY_ELIGIBLE` decision.
The authorized user can discover why an unavailable code is excluded without
seeing a raw CIS/DataMatrix or foreign-tenant information. This card changes no
code to `available` and does not make any code allocatable.

**Vertical boundary.** C1 contains source-population inventory, failed-binding
outcome classification, mandatory local-use and ownership checks, stable masked
code reference, decision-input/evidence identity, stable reason category,
append-only decision audit, reconciliation totals, and the authorized existing
read surface or an explicit `ui_change` escalation. It is independently useful:
it restores explainable pool truth for all affected historical rows and exposes
the exact safe population from which a later recovery may operate.

**Safety rules.** A code is `RECOVERY_ELIGIBLE` only when current evidence
definitively proves no external binding/use, no local consumption or commitment,
same tenant/seller/product-pool ownership, no independent invalidation and no
contradiction. Timeout, missing response, foreign or conflicting evidence,
unknown identity and stale data fail closed to an unavailable reason. `void`,
`error`, `failed` and an empty reason are never acceptable final explanations.
The register cannot reveal whether a foreign record exists, and ordinary audit,
Git evidence and user output contain only a masked/fingerprinted code reference.

**Acceptance cases for S15.**

| ID | Fixture / oracle | Expected result |
| --- | --- | --- |
| `D17-C1-AC01` | Same-tenant/seller `void` code with a definitive external binding failure, no local use, valid pool/product ownership and no invalidation | One `RECOVERY_ELIGIBLE` decision is recorded with complete masked audit evidence; the code remains non-allocatable until C2 and source totals reconcile. |
| `D17-C1-AC02` | Timeout, lost response, unavailable reconciliation, or contradictory local/external binding evidence | Code remains unavailable with the distinct unknown/contradictory-outcome reason; no recovery candidate is produced. |
| `D17-C1-AC03` | Confirmed external binding/use, local reservation/application/print/shipment, or independent manual/defect/policy invalidation | Code remains unavailable with the applicable stable reason and stays outside every allocation path. |
| `D17-C1-AC04` | Matching code, seller, product or binding evidence exists only in another tenant or seller | The foreign record is neither read as recovery evidence nor disclosed; no record in either scope changes. |
| `D17-C1-AC05` | Historical reasonless `void` rows and a mixed batch containing eligible, unknown, invalid and failed-to-evaluate rows | Every input row has one explicit disposition, totals reconcile to the full source population, and no row silently disappears or becomes available. |
| `D17-C1-AC06` | Authorized read-back of an unavailable code | Existing authorized read surface shows its understandable reason and safe next condition; if no such surface exists, classification is amended with `ui_change` before S16 and no implementation proceeds on an invisible reason. |

### `BLG-D17-C2` - Atomic recovery of a definitively unbound marking code

**Observable operational result.** A still-current C1 `RECOVERY_ELIGIBLE`
code returns exactly once to the correct `available` pool. The failed attempt
is closed, the state correction and available-count effect commit as one
business operation, and durable audit plus post-write read-back prove the
result. A row that is no longer safe remains unavailable with its reason while
other independent rows retain their own result.

**Vertical boundary.** C2 consumes only a C1 decision with current evidence and
contains mutation-boundary authorization/tenant/seller/product checks, fresh
external-outcome and local-use checks, atomic failed-attempt closure and code
state/pool update, idempotency, per-code isolation, append-only recovery audit,
available-count reconciliation and post-write read-back. It also supplies a
restartable historical-backfill path and an honest restore rehearsal. This is
one card because a state update without allocation/count truth, stale-evidence
protection, audit and read-back would leave a warehouse-unsafe outcome.

**Safety rules.** C2 never trusts a prior preview, queued job or client tenant
field at write time. A concurrent reservation, binding, shipment, ownership or
state change wins over stale recovery and stops that row without overwriting the
newer fact. Retries, duplicate requests, worker replay and restart cannot
duplicate a code, repeat an external side effect, erase a later decision or
turn an ambiguous row into `available`. No mutation moves ownership, deletes
history, rewrites a prior reason or returns a code with any uncertain outcome
to allocation, reservation, printing, application or shipment.

**Acceptance cases for S15.**

| ID | Fixture / oracle | Expected result |
| --- | --- | --- |
| `D17-C2-AC01` | Current C1-eligible same-tenant/seller code with definitive failed external binding and no local use | Failed attempt closure, code transition to `available`, correct available-pool count and append-only audit commit atomically; read-back sees the code once in its original eligible pool. |
| `D17-C2-AC02` | C1 decision becomes stale through concurrent reservation, successful binding, application or shipment | Recovery rejects/reclassifies only that row, preserves the newer fact and records an explicit stale/concurrent reason; no available-count increase occurs. |
| `D17-C2-AC03` | Unknown, contradictory, confirmed-used, manually invalidated or foreign-scope row supplied to apply | No recovery or foreign disclosure occurs; the code remains excluded with its stable reason. |
| `D17-C2-AC04` | Duplicate request, retry, worker replay and restart after success or during a mixed batch with one injected failure | Each code has one durable outcome: successful recovery is not duplicated, unsafe/failed rows remain unavailable, independent valid rows complete, and totals/read-back reconcile. |
| `D17-C2-AC05` | Existing reasonless historical `void` rows through inventory, decision and apply; old reader/writer active during additive rollout | Only currently eligible rows recover; the compatibility path preserves old readers/writers while preventing new reasonless `void` rows. |
| `D17-C2-AC06` | Recovery followed by later legitimate use and restore/rollback rehearsal | Restore can stop new recovery or safely restore only eligible newly changed rows; it never erases later use or append-only audit and does not claim unsafe data reversal. |

## Delivery order and ownership boundaries

1. C1 precedes C2. A bulk `void` to `available` update, direct repair script
   or operator convenience action is not a substitute for the per-row,
   evidence-bound decision register.
2. C2 consumes a current C1 decision only; it rechecks every safety condition
   at the mutation boundary. C1 eligibility is not a reusable permission after
   evidence, ownership or lifecycle changes.
3. `S13 ARCHITECT_PLAN` owns the authoritative state machine, persistence and
   additive migration choices, transaction/lock/resource graph, source of
   truth for external outcome, job/retry shape, compatibility path, exact
   unavailable-reason taxonomy, authorized read surface, backfill and restore
   policy. S12 chooses none of those mechanisms.
4. The S11 requirement that reasons are user-discoverable is mandatory. S13
   must name an existing authorized read surface that satisfies it. If that is
   impossible without visible change, the task must add `ui_change` and return
   through S09/S10 before S16; this cut does not bypass design or live Product
   Browser acceptance.
5. `BLG-F01` remains an explicit dependency for canonical blocker/dependency
   registry integration. Its unfinished status is not permission to omit C1/C2
   reasons, the affected operation or their controlled reconsideration path.
6. S15 maps every acceptance row to deterministic isolated fixtures, reset,
   executor and automation binding. S14 independently attacks uncertain
   external outcome, stale evidence, cross-tenant access, duplicate execution
   and unsafe restore. S20/S22/S23 prove the required tenant-isolation,
   migration/backfill, integrity and restore evidence without live marketplace
   or production operations.

## Explicit exclusions

This cut authorizes no implementation, schema or migration choice, direct data
repair, production data inspection or mutation, live WB/Ozon call, new manual
release action, secret access, commit, push, merge, deployment, release
authorization, or Product/Browser acceptance. It does not alter packing,
marking, shipment or allocation sequences beyond the later approved truth of
which code is safely `available`.

## Handoff

**Next stage:** `S13 ARCHITECT_PLAN`, owned by `solution-architect`, because
the task is high risk with `database_change` and contains two dependent vertical
cards. The architect receives this cut, the S11 Product contract and the C1/C2
acceptance matrix. A changed card boundary, unavailable-reason/read-surface
finding, or changed Product contract requires S12 rework before S16.

## Verdict

`TASK_CUT_READY`: C1 provides a complete, safe and explainable decision
population; C2 independently delivers atomic recovery only for that proven
population. Together they preserve the Product fail-closed invariant without
splitting one warehouse outcome into disconnected backend, UI or repair work.

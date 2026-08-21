# S12 TASK_CUT - BLG-C01

## Verdict

`TASK_CUT_READY`

## Atomic vertical card

`BLG-C01` remains one atomic release card: **release the approved optional
FBS-packing behaviour only after an owner authorizes one immutable candidate
SHA for one named tenant**.

It is not safe to split this into separate deploy, migration, configuration or
operator-check cards. None of those fragments leaves a safe independently
observable warehouse result: the outcome exists only when the same approved
artifact, additive migration, tenant-scoped configuration and operator proof
remain bound together. The controller stages following this cut keep the
required independent checks and authorization boundaries intact.

## Card contract

**Observable result.** For the owner-authorized tenant with
`fbs_packing_required = false`, an eligible FBS supply proceeds through the
existing next applicable step without a synthetic packing task. A tenant whose
value is `true`, absent, unreadable or unknown retains the existing packing
gate. Historical supplies retain their truthful audit distinction between an
automatic no-packing path and physical packing completion.

**Required evidence before release authorization.** S13-S15 must turn the
S11 contract into an implementation and proof plan covering the additive
migration and safe default, tenant isolation, retry/idempotency, persisted
read-back and reload, required-packing regression, and the no-packing journey.
S23 must bind the candidate to immutable artifact digests. S26 must provide
the full 40-character candidate SHA, manifest, migration order and
compatibility proof, authorized tenant/configuration operation, smoke/stop/
rollback procedure, and live trace plan.

**Not part of this card.** It does not approve unrelated FBS process changes,
skipping independent warehouse or marketplace gates, global optional packing,
secret access, live marketplace operations, or a different candidate SHA.

## Delivery order and ownership boundaries

1. S13 creates the high-risk release resource graph and candidate-proof plan.
2. S14 independently falsifies that plan.
3. S15-S26 complete the required cases, implementation, review, integration
   and release-preparation receipts without promoting anything live.
4. S27 is the future owner-approval stopper: only a separate owner decision
   that names the exact full `release_candidate_sha`, immutable manifest and
   target tenant can authorize exact-SHA promotion and its configuration
   change.
5. S28 may run only after S27 proves the deployed runtime and artifacts match
   that same approved SHA and manifest; it owns production smoke, rollback and
   trace evidence.

## Explicit boundary for this stage

S12 performs no implementation, commit, push, merge, deployment, live
migration, tenant configuration change, production verification, release
authorization or exact-SHA approval. Until the separate S27 owner decision and
the subsequent S28 proof exist, the furthest honest release state is
`READY_FOR_RELEASE`, never deployed or `DONE`.

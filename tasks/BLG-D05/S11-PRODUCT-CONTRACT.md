# S11 PRODUCT_CONTRACT_APPROVAL - BLG-D05

## Product decision

Product approves a fail-closed reconciliation of the Denmarcs marking-code
pool. The purpose is to return only proven codes to normal warehouse use and
to keep every ambiguous code unavailable until a data owner confirms its
product identity.

Every affected code must receive one of two business classifications:

- `CONFIRMED_LINK` (`Подтверждена привязка`) - the code has one proven,
  current product target inside the same tenant and seller;
- `REVIEW_REQUIRED` (`Требует проверки`) - the target is absent, conflicting,
  non-unique or supported only by inference.

Only `CONFIRMED_LINK` may make an otherwise eligible code available to the
existing warehouse lifecycle. `REVIEW_REQUIRED` is a quarantine state: it
must not contribute to an available-code count and must not be selected,
reserved, printed, applied, introduced, transferred or shipped automatically.
An empty, unknown or unreadable classification fails closed to
`REVIEW_REQUIRED`.

## Confirmation policy

A link is confirmed only when all mandatory identity and ownership evidence
agrees:

1. The code, source pool/import, historical product and target product belong
   to the same tenant.
2. The code, source pool/import and target product belong to the same seller.
3. The code GTIN and target product marking identity match exactly after the
   already approved, lossless GTIN normalization. A SKU or product name is
   supporting evidence only and cannot establish a link by itself.
4. Where an `OLD/` card and a current card are involved, the historical-to-
   current lineage is explicitly confirmed by the Denmarcs data owner from a
   reviewable mapping. The `OLD/` prefix, similar text, sort order or newest
   synchronization timestamp is not confirmation.
5. The result identifies one current canonical target for the code. Zero
   candidates, multiple current candidates, conflicting GTIN/SKU evidence,
   duplicate product cards or a target outside the tenant or seller requires
   `REVIEW_REQUIRED`.
6. The code is still operationally eligible under its existing lifecycle.
   Reconciliation must not revive a code that is reserved, printed, applied,
   introduced, shipped, transferred, defective, replaced or void, and must
   not rewrite its historical product usage.

Candidate generation may be automated, but candidate confidence is not
authorization. A batch may auto-apply only rows whose mandatory evidence is
complete, internally consistent and uniquely identifies the target under this
policy. Any exception quarantines the individual code; it must not force a
best-effort choice or contaminate otherwise valid rows in the batch.

If one shared pool currently exposes the same unassigned codes to several
product cards, that pool association alone is not a confirmed code-to-product
link. Downstream design must ensure that a code classified for one canonical
target cannot be counted or consumed for another target.

## Operational outcome

After reconciliation:

- confirmed codes participate in the same existing marking-code lifecycle as
  codes imported with a valid product link;
- doubtful codes remain durably present and discoverable for controlled data
  review, with a clear reason, but are invisible to automatic allocation;
- the warehouse operator receives no new confirmation step and no silent
  substitution of one product for another;
- a shortage caused by quarantined codes remains an honest shortage. WMS must
  not consume a doubtful code merely to let packing or shipment continue;
- repeat execution, retry, reload and partial batch failure preserve the same
  classification and never create duplicate links or duplicate use;
- a later correction is a new reviewed decision. It does not erase the prior
  classification or its evidence.

This is a data-policy change, not a redesign of the operator process. It does
not approve a new warehouse screen, a new packing action, deletion of `OLD/`
cards or changed marking-code lifecycle rules.

## Tenant and authorization safety

- Every read, candidate set, count, mutation and read-back is scoped by the
  authorized tenant. Seller ownership is checked independently inside that
  tenant.
- A product, pool, import or code from another tenant or seller is never a
  candidate, even when GTIN, SKU, barcode or name is identical.
- Cross-tenant and cross-seller identifiers must not reveal whether the foreign
  record exists and must not change either side.
- Authorization is rechecked at the mutation boundary, not trusted from a UI,
  exported mapping or earlier preview.
- Batch processing is atomic per code and idempotent. A valid row cannot make
  an invalid row usable, and a failure must not leave a code both linked and
  quarantined.
- Tenant, seller and code ownership cannot be changed as a side effect of
  reconciliation.

## Audit and evidence contract

Every proposed and applied decision must be reconstructable without exposing
raw marking codes in ordinary logs or Git evidence. The durable audit trail
must retain:

- policy version, batch/correlation id and decision time;
- authorized tenant and seller, actor or controlled job identity;
- stable masked code reference or fingerprint, source import/pool reference
  and source artifact hash when available;
- prior classification and link, candidate products, selected target and final
  classification;
- each mandatory evidence result, explicit reason code and data-owner approval
  reference when manual confirmation was required;
- mutation outcome, error/skip reason and post-write read-back result.

Audit events are append-only. Reclassification or reassignment creates a new
event with before/after values and a reference to the decision it supersedes;
it must not overwrite history. General logs, receipts, screenshots and Git
artifacts use masked identifiers and stable fingerprints. Full CIS/DataMatrix,
tenant-sensitive payloads and source documents stay out of general evidence.

## Migration and reconciliation boundaries

S12 and S13 must preserve the following product constraints in the task cut
and architecture plan:

- first produce a non-mutating inventory with totals for confirmed,
  review-required, skipped and already-consumed codes, reconciled to the source
  population;
- preserve existing lifecycle status and historical events; reconciliation
  changes only the approved link/classification surface;
- apply changes in restartable, idempotent units with stable decision inputs,
  explicit partial-failure reporting and post-write read-back;
- stop a row on changed evidence, concurrent use or ownership mismatch rather
  than applying a stale preview;
- provide an additive compatibility path plus restore/rollback rehearsal that
  can remove newly applied links/classifications without deleting codes or
  falsifying events created after a code entered operational use;
- retain unresolved rows for later review instead of dropping, voiding or
  silently attaching them.

The declared dependency on `BLG-F01` supplies the canonical block/dependency
registry integration. It does not authorize bypassing this contract while that
card is incomplete: the no-auto-use rule and its reason must remain explicit
in BLG-D05 evidence and downstream cases.

## Required downstream proof

S15 must create direct and breaker cases for at least:

- unique confirmed `OLD/` to current-card mapping;
- missing, multiple and conflicting candidates;
- same GTIN/SKU in another tenant or seller;
- code with a non-available lifecycle status;
- stale preview and concurrent reservation/use;
- partial batch failure, retry and duplicate execution;
- confirmed and quarantined counts, allocation exclusion and read-back;
- reassignment with preserved audit history;
- migration compatibility, integrity reconciliation and restore/rollback.

S22 and S23 must prove the negative-authorization and cross-tenant isolation
receipts required by `tenant_sensitive`, plus migration/backfill integrity and
rollback evidence required by `database_change`. No production Denmarcs data,
live WB/Ozon operation or live database mutation is authorized by this S11
decision.

## Out of scope

No code implementation, schema choice, direct data repair, product merge or
deletion, `OLD/` visibility change, operator UI change, commit, push, deploy,
secret access, live Denmarcs/WB/Ozon call or production mutation is performed
or approved at S11.

## Verdict

`PRODUCT_CONTRACT_APPROVED`: confirmed same-tenant, same-seller and uniquely
evidenced links may return eligible codes to normal use; every uncertain code
fails closed to a durable review-required classification with no automatic
use, complete audit evidence and explicit tenant-isolation proof.

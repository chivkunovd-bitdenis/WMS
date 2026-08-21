# S15 independent case audit - BLG-D05

## Verdict

`CASE_AUDIT_FAILED`

This is an independent `case-auditor` review of the exact S15 package. It
does not change controller state, approve S16, or authorize development.

## Audited package

- `S15-CASES.json`: `sha256:77c3fcf66febcf4a7c4c21e5502cb7eeed62d2d3c10d0a84ae5ad41df172f93c`
- `S15-CASE-FACTORY.md`: `sha256:7ea1d4376e4cd98a8432c0768e83127d358a2b9ea19be45f300a49dbf4147285`
- Oracles checked: S11 `sha256:d1f431eb5b923cc531d88112663b5d380bdb75d39a5bf75864358de5e571824a`, S12 `sha256:e4eb2d50419735149ba2769d2f9cf2fa120188351508bd2d6b47cb3d5ed75b9a`, and S13 `sha256:92e455d12ff8ab0e3048d463e8cdab8aa7977ab5d8bb86e2ff1e31d94223ae58`.

## What is covered

Every S12 acceptance row has a direct GOLD case. The package also has local
synthetic fixtures, deterministic reset, masked read-back, and a planned S19
binding for tenant/seller isolation, quarantine/no-auto-use, idempotency,
stale and concurrent apply, partial failure, migration compatibility, and
safe/skipped restore branches. It remains within the BLG-D05 data-task scope.

## Missing independent breaker coverage

S15 requires direct and independent breaker coverage for each changed behavior
and process journey. The exact package cannot prove that requirement:

1. `S15-CASES.json` records only `status: GOLD`; it has no `variant`,
   `case_kind`, or independent `case-breaker` provenance. Its `coverage`
   entries are untyped lists, so the Markdown claims of direct versus breaker
   coverage cannot be machine-checked or shown to be independently authored.
2. `D05-C2-AC02` has only `D05-C2-08` in the JSON coverage matrix. The
   Markdown calls `D05-C2-10` its breaker, but that case fixture contains only
   approved rows and forced mutation/crash recovery; it does not exercise the
   required `REVIEW_REQUIRED`, unknown, unreadable, expired, or
   missing-approval decision variants from AC02.
3. `D05-C2-AC04` has only `D05-C2-10` in the JSON coverage matrix. The
   Markdown calls `D05-C2-09` its breaker, but that case is a stale/concurrent
   reservation race; it does not independently break the AC04 mixed
   partial-failure, retry, and duplicate-execution oracle.

## Required rework and blocker

Add independently authored, deterministic breaker cases for `D05-C2-AC02`
and `D05-C2-AC04`; record their direct/breaker role and `case-breaker`
provenance in the JSON coverage contract; then align the Markdown matrix with
the same case IDs and fixture assertions. The current blocker remains
`CASE_AUDIT_REQUIRED`; S16 must not be accepted from this package.

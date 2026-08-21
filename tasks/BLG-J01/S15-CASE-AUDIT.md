# S15 Independent Case Audit - BLG-J01

## Scope and exact package

This is an independent `case-auditor` review of the exact S15 package for the
single low-risk UI card `BLG-J01-C1`. It does not decide S16 Product approval,
change implementation scope, or modify controller state.

- Auditor role: `case-auditor`
- Audit model/tier: `gpt-5.6-terra` / `moderate`
- Baseline SHA: `69c271678782d7dcfa39df97cd905cbee1678727`
- `S09-UX-CONTRACT.md`: `sha256:9253127857841e190dba24a8bb6c1d678c97e2cb35e23d89cd2150e042b4d152`
- `S11-PRODUCT-CONTRACT.md`: `sha256:8e0cd33750ba6f60a4d37720bc02a81baee1fc6cd1d0736682caf1e2b0d2aaf0`
- `S12-TASK-CUT.md`: `sha256:cdb092cc50845f4e0400c543113d21ae6e8471419a751306737427674aff6841`
- `S15-CASE-FACTORY.md`: `sha256:aed41e87b55a10b053e55af3c0dd3434c63a44f6c02a3a63554a3e9f3fbd15af`
- `S15-CASES.json`: `sha256:720b89264d70d4d97a036abad1590da1e3cf8cd525c1ec14fcb3ac11381cbf4a`

These hashes match the package recorded by `S16-PRODUCT-BEFORE-DEV.md`.

## Minimum closure audit

| S12 acceptance row | Correct GOLD case(s) | Audit result |
| --- | --- | --- |
| AC01: accepted exact six-symbol SGTIN tail and ready next entry | `BLG-J01-AC01`, `BLG-J01-AC05` | Covered. AC01 asserts the exact approved text for fixture tail `A1B2C3`; AC05 proves the latest accepted local result replaces the prior context without a new acknowledgement. |
| AC02: non-KIZ UIN/IMEI/GTIN | `BLG-J01-AC02` | Covered. Each listed non-KIZ kind keeps its current display and has no KIZ wording. |
| AC03: absent, short, long, or malformed supplied tail | `BLG-J01-AC03` | Covered. The complete line is omitted; the case prohibits padding, new truncation, or a guessed value. |
| AC04: rejected or transport-failed add with and without prior KIZ | `BLG-J01-AC04` | Covered. The deterministic failure cannot promote raw rejected input; only an already confirmed fixture context may remain. |
| AC05: two rapid successful additions/reloads | `BLG-J01-AC05` | Covered. The latest confirmed local result is `D4E5F6`, with no stale-tail leakage or added interaction. |
| AC06: long identity and narrow viewport | `BLG-J01-AC06` | Covered. The 375x812 fixture checks wrapping, all six symbols, visible/reachable entry and dialog action, and no horizontal scrolling. |
| AC07: dialog close or order change | `BLG-J01-AC07` | Covered. The case closes order A and opens order B with no accepted KIZ tail, then verifies no cross-order retention. |

The seven mapped cases are all `GOLD`; there are no uncovered applicable S12 rows.

## Oracle fidelity, fixtures, and S19 binding

The explanatory KIZ wording is positively asserted only by AC01, AC05 and AC06,
where the fixture returns an accepted `sgtin` with an exactly six-symbol tail.
AC02, AC03 and AC04 are negative guards and prohibit that wording for non-KIZ,
non-exact, and rejected data. This matches the S09/S11 oracle and does not turn
the label into a claim about another identifier kind or unconfirmed input.

Every case names fixture version `BLG-J01-S15-v1`, a fresh Playwright browser
context with local route mocks, and executable reference
`frontend/tests-e2e/ff-fbs-supply.spec.ts#BLG-J01-AC01` through
`#BLG-J01-AC07`. All seven bindings are `PLANNED_FOR_S19`. The fixture contract
forbids external egress and resets state per case, so the planned S19 work can
make each oracle runnable without changing it.

## Scope boundary

The cases stay within the approved display-path card. API observations in AC04
and AC05 explicitly limit themselves to existing locally mocked request flows
and assert that the card adds neither endpoint nor retry policy. Database,
worker, marketplace, print, and authorization assertions are explicitly N/A;
there is no case for parser, persistence, API contract, database, worker,
marketplace, print, or authorization behavior. No scope expansion was found.

## Verdict

`CASE_AUDIT_PASSED`

Blocker: none in the audited S15 package. The controller remains `WAITING` at
S16 until the orchestrator registers this independent evidence and Product
re-runs S16 against these unchanged package hashes.

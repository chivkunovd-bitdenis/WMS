# S15 CASE_AUDIT - BLG-J02

Role: `pipeline-case-auditor` / `pipeline-reviewer`  
Agent: `codex-pipeline-case-auditor-blg-j02-s15`  
Verdict: `CASE_AUDIT_PASSED`

## Independence

The audited package was produced by `codex-pipeline-ba-blg-j02-s15`. This
auditor did not write `S15-CASE-FACTORY.md` or `S15-CASES.json`, did not change
their expectations, and did not perform a controller transition.

## Exact package evidence

- `S15-CASES.json`: `426bec0805aa94ca3655339f08b2e9918f30d2424ff3c81ffe2f75958438c697`
- `S15-CASE-FACTORY.md`: `7e2a4bcb9657e1c6a6be6917b6ad953e9cbc7cddaafcfd577104152498f35302`
- Pre-audit `S15-CASE-AUDIT.md` stub: `49aa6ba362156375d63716dbecf53f85333fecc2db219cad19ecc8078d3b677d`

The seven case IDs are unique and contiguous from `J02-C1-01` through
`J02-C1-07`. Every case is `GOLD`, uses fixture
`blg-j02-expired-session-local-v1`, declares a Playwright executor and planned
S19 binding, and contains an oracle, read-back assertion and reload assertion.
All case references in the coverage matrix resolve to those seven case IDs.

## Coverage verdict

| Contract requirement | Direct and breaker evidence | Result |
| --- | --- | --- |
| Only structured `invalid_token` from the active portal `GET /auth/me` enters recovery | `J02-C1-01`, with generic and non-profile failure breakers in `J02-C1-04` | Covered |
| Fulfillment and seller session isolation | Parameterized portal variants and byte-for-byte other-session assertion in `J02-C1-01` | Covered |
| Exact Russian notice and no raw technical/token/marketplace-key text | DOM and visible-text assertions in `J02-C1-01`; narrow rendering assertion in `J02-C1-07` | Covered |
| Verified same-portal return, query/hash preservation and replacement history | `J02-C1-02`, with repeat and Back breakers in `J02-C1-05` | Covered |
| Absent, malformed, absolute, protocol-relative, cross-portal, unknown, removed and role-forbidden targets | Parameterized rejection and portal-specific silent fallback in `J02-C1-03` | Covered |
| One-time target consumption, duplicate-submit protection and repeated-expiry safety | Request counters, history and stale-target checks in `J02-C1-05` | Covered |
| No replay of reads, mutations, scans, prints or marketplace operations | Action and sentinel counters in `J02-C1-06` | Covered |
| Existing bad-password, network, password-setup, generic-401, non-401 and role-mismatch behavior | `J02-C1-04` | Covered |
| Both portal compositions at `360 x 640 CSS px` | Six portal/state combinations, overflow and button-bound checks in `J02-C1-07` | Covered |

`python3 scripts/pipeline/run.py validate --task-id BLG-J02` passed against the
audited package. No uncovered applicable S09, S10, S11 or S12 row and no case
oracle conflict was found.

## Handoff

The orchestrator may register this independent verdict and let S16 Product
evaluate the exact hashed package. This audit does not approve S16, Dev,
release, deployment, live calls or credential access.

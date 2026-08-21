# BLG-C02 - S03 RESEARCH REWORK CLOSURE

## Passport

- Rework owner: `pipeline-ba:codex-blg-c02-research-rework`.
- Date: `2026-08-21`, Europe/Moscow.
- Blocker: `SECURITY / RESEARCH_CONTRACT_GAPS`.
- Scope: public contract artifacts and synthetic case design only.
- External operations: no production or sandbox calls, credential access, secret pages, release,
  deploy, S27 or S28 actions.
- Result: S03 is corrected and ready for a fresh independent S04 review; this is not a
  `RESEARCH_PASSED` verdict.

## RC-01 closure

The prose auth table and machine `AUTH_MODES` row now preserve four separate token modes. Personal
and Test remain Bearer-only. In the partner-service context documented by SRC-13, both Service and
Base require `Authorization` plus `X-Client-Secret`; a Base-token request without the service secret
is forbidden. The contract does not generalize that header to unrelated requests.

The `AUTH_401_403` row and dossier now require synthetic Service and Base cases for token or secret
verification failure (`401`) and for a missing secret, token-secret mismatch or disallowed pairing
(`403`). Base fixtures explicitly cover missing, invalid, expired, withdrawn, mismatched and
disallowed `X-Client-Secret` outcomes without reading a real credential or retaining WB response
text.

The aggregate no-leak proof now uses distinct Service and Base `X-Client-Secret` canaries. It scans
structured WB events, the existing error logger, application/client/access/worker logs, API exception
output, traces, metric labels and persisted evidence after success, every HTTP error including all
Base `401/403` fixtures, and transport failures. Any raw Base token or secret match fails the case.

## Resume condition

- Base partner-service header contract corrected in prose and machine rows: closed.
- Base synthetic `401/403` coverage, including all reviewer-named secret outcomes: closed.
- Base secret propagated to aggregate sink-wide zero-leak proof: closed.
- Live calls and credential access required: no.

The next controller action is `resume` at S04 followed by a new packet/dispatch for an independent
`pipeline-reviewer`. The rework author must not execute S04 `advance`.

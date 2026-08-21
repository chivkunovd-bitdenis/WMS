# BLG-C02 - S04 RESEARCH_CRITIC

## Passport

- Role: `pipeline-reviewer`, independent `research-critic`.
- Reviewed rework commit: `ad8da528f8064712162ae75bfc48cb64ad3ff050`.
- Model tier: `gpt-5.6-sol`, `expensive`.
- Review date: `2026-08-21`, Europe/Moscow.
- Inputs: `S03-EXTERNAL-CONTRACT-DOSSIER.md`, `S03-capability-matrix.json`, controller S04
  packet, and independently located public WB documentation.
- External operations: no production or sandbox API calls; no credentials, secret pages, deploy,
  release, S27 or S28 actions.
- Verdict: `RESEARCH_REWORK`.

## Result

The rework closes four of the five original finding groups. It now makes zero raw-data leakage an
end-to-end invariant across API and worker sinks, including `log_wb_client_error`; maps `402`,
`406`, and verified-N/A `451`; specifies strict absent/malformed/numeric rate-limit parsing; and
separates official sandbox classification from deterministic MockTransport/emulator proof without
authorizing live calls.

Research cannot pass because the auth matrix contradicts the current official WB partner-service
contract for the Base token. This is the same `RESEARCH_CONTRACT_GAPS` blocker, not a new scope.

## Blocking finding

### RC-01 - Base token incorrectly excludes X-Client-Secret

The dossier says Base uses only `Authorization: Bearer <token>` and no `X-Client-Secret`. The machine
row `AUTH_MODES` repeats that Base and Test use Bearer only. Current official WB documentation for
partner services states that the service secret is mandatory for requests made with both Service
and Base tokens; using a Base token without the service secret is not allowed.

This mismatch leaves the original requirement for Service/Base `X-Client-Secret` uncovered and can
produce a false S15 case design: a Base-token credential canary would be omitted from request
fixtures and from sink-wide leakage assertions.

Required rework:

1. Correct the prose auth table and `AUTH_MODES` machine row so Base has both `Authorization` and
   `X-Client-Secret` in the applicable partner-service context; keep Test separate according to its
   documented sandbox contract.
2. Correct `AUTH_401_403` cases so Base-token missing, invalid, expired, withdrawn, mismatched, or
   disallowed service-secret outcomes are classified without logging either credential or raw WB
   response text.
3. Extend the later S15 synthetic fixture and aggregate zero-leak proof explicitly to the Base-token
   `X-Client-Secret` lane. No real credential or live request is needed.

Official source:

- https://dev.wildberries.ru/knowledge-base/articles/019d49a1-bd37-76b4-931d-fa5fa437b85e

## Original blocker closure matrix

| Finding group | Review result | Evidence in rework |
|---|---|---|
| Zero leakage across API/worker sinks | Closed | Denylist and aggregate canary scan include structured event, `log_wb_client_error`, app/httpx/httpcore/access logs, API exceptions, worker logs, traces, metric labels, and persisted evidence. |
| Auth modes and 401/403 | Open | Service is covered, but Base incorrectly excludes `X-Client-Secret`; machine rows would generate incomplete cases. |
| 402/406/451 applicability | Closed | `402` and stock-update `406` are applicable; `451` is explicitly N/A for the current call inventory with safe unknown-4xx fallback. |
| Rate-limit aggregation and parsing | Closed | Personal/Service/Base/Test aggregation plus absent, malformed, negative, overflow, and numeric Retry/Limit/Reset cases are specified. |
| Official sandbox and deterministic proof | Closed | Exact content/marketplace/supplies sandbox hosts, Test-token restriction, lower limits, zero authorized sandbox requests, and deny-egress MockTransport/emulator proof are explicit. |

## Resume condition

S03 must correct the Base-token secret contract in prose and machine rows and propagate it to the
required synthetic 401/403 and sink-wide leakage cases. A fresh independent S04 review is required;
until then `RESEARCH_PASSED` is prohibited.

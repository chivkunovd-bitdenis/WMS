# BLG-C02 - S04 RESEARCH_CRITIC

## Passport

- Role: `pipeline-reviewer`, independent `research-critic`.
- Reviewed BA repair commit: `18e5f207a60bb33a830bee568c436d4006862b84`.
- Model tier: `gpt-5.6-sol`, `expensive`.
- Review date: `2026-08-21`, Europe/Moscow.
- Inputs: `S03-EXTERNAL-CONTRACT-DOSSIER.md`, `S03-capability-matrix.json`,
  `S03-RESEARCH-REWORK-CLOSURE.md`, the current S04 controller packet and the official WB
  partner-service authorization documentation.
- Scope: exact RC-01 re-review only; no application code review or modification.
- External operations: public documentation read only; no production or sandbox API calls,
  credentials, secret pages, deploy, release, S27 or S28 actions.
- Verdict: `RESEARCH_PASSED`.

## Result

The BA repair closes RC-01 without broadening the task. The current official WB partner-service
contract states that both Service and Base token requests require `Authorization` plus
`X-Client-Secret`, and that Base without the service secret is forbidden. The repaired prose and
machine matrix now preserve that requirement while keeping Personal and Test Bearer-only in their
documented contexts.

The synthetic Base lane now covers every reviewer-required service-secret outcome: missing,
invalid, expired, withdrawn, mismatched and disallowed. These cases retain only status and
`auth_rejected`; neither credential nor raw WB response text is an allowed diagnostic field.

The Base secret is also propagated into the aggregate zero-leak proof as a distinct canary. The
required scan spans structured WB events, `log_wb_client_error`, application, HTTP client, access
and worker logs, API exception output, traces, metric labels and persisted test evidence. It runs
across success, every HTTP error including all Base `401/403` fixtures, and transport errors. Any
Base token or secret match fails the later case.

## RC-01 closure matrix

| Required correction | Verdict | Evidence |
|---|---|---|
| Base partner-service requests require `Authorization` and `X-Client-Secret` | Closed | Dossier section 6 and machine row `AUTH_MODES` require both headers and forbid Base without the service secret. |
| Base secret failures cover missing, invalid, expired, withdrawn, mismatched and disallowed | Closed | Dossier sections 6 and 13 plus machine row `AUTH_401_403` enumerate all six synthetic outcomes. |
| Base-secret canary participates in aggregate zero-leak verification | Closed | Dossier section 13 and machine row `API_WORKER_SINKS` require a distinct Base canary across logs, errors, traces, metrics and evidence for Base `401/403` and other outcomes. |
| Review requires no real credential or live call | Closed | Matrix has `live_calls_performed=false`; dossier and closure explicitly prohibit credential access and live sandbox/production calls. |

## Independent source check

Official WB source, updated `2026-04-03`:

- https://dev.wildberries.ru/knowledge-base/articles/019d49a1-bd37-76b4-931d-fa5fa437b85e

It states that the service secret is mandatory for requests using both Service and Base tokens and
lists the relevant `401` secret-verification and `403` missing/mismatched/not-allowed classes. The
S03 contract uses synthetic cases and a stricter denylist; it does not require a real secret to
validate the logging contract.

## Release boundary

`RESEARCH_PASSED` approves only the corrected S03 research contract. It does not approve an
implementation, enable logging, authorize a release, or permit S27/S28. Because BLG-C02 has the
`release_change` trait, release still requires separate owner approval for the exact SHA at the
controller release stage.

## Blockers

None for S04. The next stage must be selected by the controller.

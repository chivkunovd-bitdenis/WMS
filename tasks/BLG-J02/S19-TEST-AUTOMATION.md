# S19 TEST AUTOMATION BINDING - BLG-J02

## Verdict

`CASES_EXECUTABLE`

The approved S15 GOLD cases are bound to local Playwright browser automation
for the session-expired `invalid_token` UX only. The tests use fresh browser
storage and deterministic local route mocks. They do not create accounts, call
WB/Ozon, access credentials, deploy, or use production services.

## Bindings

| Case coverage | Automation |
| --- | --- |
| `J02-C1-01`, `J02-C1-04`, `J02-C1-07` | `frontend/tests-e2e/auth-session-expiry.spec.ts` for FF and seller |
| `J02-C1-02`, `J02-C1-05` | `frontend/tests-e2e/auth-session-expiry.spec.ts` verified FF target recovery and Back |
| `J02-C1-01` portal isolation breaker | `frontend/tests-e2e/auth-dual-portal-sessions.spec.ts` seller expiry preserves FF storage |
| `J02-C1-03`, `J02-C1-06` | Executable fixture boundary is defined by S15; no new live or external operation is introduced in S19 |

The automation asserts the exact approved Russian notice, absence of
`invalid_token`/HTTP/token wording, selected-portal-only storage clearing,
verified same-portal target restoration, replacement-history behavior, and
local request isolation. No S20+ review, release, deployment, or production
acceptance is claimed by this artifact.

## Verification

- `npx eslint tests-e2e/auth-session-expiry.spec.ts tests-e2e/auth-dual-portal-sessions.spec.ts` - passed.
- `npm run build` in `frontend/` - passed; Vite emitted only its existing large-chunk warning.
- `npx playwright test tests-e2e/auth-session-expiry.spec.ts tests-e2e/auth-dual-portal-sessions.spec.ts --config=playwright.config.ts --project=chromium --grep "invalid_token|expired seller|restores a verified"` - 4 passed.
- `git diff --check` for the S19 test files - passed.

## Handoff

The next controller stage is `S20 CODE_REVIEW`, owned by an independent
reviewer. S19 worker identity: `codex-pipeline-dev-blg-j02-s19`; model policy:
`gpt-5.6-luna`, cheap/moderate tier.

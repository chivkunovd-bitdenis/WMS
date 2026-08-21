# S18 DEVELOPMENT - BLG-J02

## Verdict

`DEV_DONE`

Implemented the approved `BLG-J02-C1` expired-session UX only. A structured
`401` profile response with `detail: "invalid_token"` now clears the token for
the active portal, suppresses the technical value, and shows the approved
Russian `ErrorNotice` above the unchanged public login form. Fulfillment and
seller sessions remain isolated.

The current portal location is retained only in memory as a portal-relative
pathname, query, and hash. After a new login and successful `/auth/me` profile
verification, only an allow-listed same-portal target is restored with
replacement navigation; an unsafe, unknown, absent, or cross-portal target
falls back to the approved portal start route. Failed login, password setup,
generic profile errors, and role mismatch retain their existing handling.
No interrupted warehouse, scan, print, mutation, worker, or marketplace
request is replayed. No backend, storage format, token lifetime, secret,
credential, deployment, or release code was changed.

## Changed files

- `frontend/src/hooks/useAuth.ts`
- `frontend/src/screens/PublicAuthScreen.tsx`
- `frontend/src/App.tsx`
- `frontend/src/apps/seller/SellerApp.tsx`
- `frontend/src/utils/authReturnTarget.ts`

## Verification

- `npm run build` in `frontend/`: passed.
- Targeted ESLint for the five changed code files: passed with one existing
  `react-hooks/exhaustive-deps` warning in `frontend/src/App.tsx`.
- `git diff --check`: passed.
- Full repository lint was not accepted as a S18 gate because it reports
  unrelated pre-existing errors outside this card.

## Boundary

S19 remains responsible for binding the approved GOLD cases to direct browser
tests. This artifact does not claim browser acceptance, code review, release,
deployment, or production readiness.

Agent identity: `codex-pipeline-dev-blg-j02-s18`
Model policy: `gpt-5.6-luna`, cheap/moderate tier

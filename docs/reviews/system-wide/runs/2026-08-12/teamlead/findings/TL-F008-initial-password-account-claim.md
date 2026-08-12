# TL-F008 — Знание email позволяет первым назначить пароль новой учётной записи

## Паспорт

- Finding ID: `TL-F008`
- Title: any unauthenticated caller who knows an invited seller/staff email can claim that account before its intended owner
- Class: `SECURITY`
- Severity: P1
- Area / scenario ID: authentication / first login
- First reviewer / independent verifier: teamlead / runtime legitimate-flow evidence by orchestrator
- Environment and SHA: static `a39530c`; staging UI attribution blocked
- Role / tenant / seller test IDs: synthetic seller first-login flow
- WB mode: N/A

## Ожидаемое поведение

- Источник правды: invited-account authentication boundary.
- Короткое ожидаемое поведение: first password setup requires a one-time proof issued to the intended person, not only a guessable email.

## Фактическое поведение и воспроизведение

- Preconditions: an account with `must_set_password=true` and knowledge of its email.
- Steps: unauthenticated POST email plus attacker-chosen password to `/auth/set-initial-password`.
- User/data effect: server sets the password and returns a bearer token for that tenant/role/seller. The intended owner later receives `password_already_set`.
- Repeatability: static path and automated tests establish the behavior; no hostile staging claim was attempted.

## Доказательства

- result screenshot: `UI-SELLER-FIRST-LOGIN__seller__1280x720__result.png` proves the legitimate setup ends authenticated in Documents; it does not prove attacker identity.
- code path: `backend/app/api/auth.py:226-259` has no authentication/one-time proof dependency; `auth_service.py:192-211` selects by email and commits the new password; `frontend/src/hooks/useAuth.ts:267-303` sends only pending email and new password.
- existing tests: `backend/tests/test_staff_users.py:58-75` and `test_seller_rbac.py:112-140` intentionally perform unauthenticated setup and receive authenticated access.

## Ущерб и граница

- Кто страдает: every newly invited staff or seller before first setup.
- Результат: account takeover with the invited role's tenant/seller access.
- Workaround: admin assigns and securely transmits an initial password instead of email-only setup; operational cost and credential handling rise.
- Почему дефект: authentication must establish the intended principal.
- Не входит: password reset for established accounts or email delivery design.

## Анализ причины

- Proven root cause: email plus mutable account flag is treated as possession proof.
- Retry/recovery: first caller wins irreversibly without an admin reset path in this finding.
- Tenant/seller implications: token is correctly scoped to the claimed account, but the caller has not proved entitlement to that scope.

## Критерий закрытия

- Given: a newly invited account and an unrelated unauthenticated caller knowing its email
- When: caller attempts initial setup
- Then: setup is rejected without a single-use, expiring proof
- And: legitimate setup succeeds once and replay fails

## Вердикт оркестратора

- Accepted: accepted by orchestrator as P1 static account-claim finding
- Second reproduction for P0/P1: safe negative/claim test required in disposable tenant
- Queue status: accepted P1; safe negative runtime closure still required

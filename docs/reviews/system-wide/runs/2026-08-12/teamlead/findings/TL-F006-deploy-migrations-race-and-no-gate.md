# TL-F006 — API и worker одновременно накатывают миграции, а deploy не ждёт CI и не доказывает версию

## Паспорт

- Finding ID: `TL-F006`
- Title: deployment can race schema upgrades and still report green from three HTTP 200 checks
- Class: `RELIABILITY`
- Severity: P1
- Area / scenario ID: release/schema/runtime alignment
- First reviewer / independent verifier: teamlead / corroborated by existing hotfix branch
- Environment and SHA: etalon `a39530c`; staging exact component versions unproven
- WB mode: N/A

## Ожидаемое поведение

- Источник правды: system review E7 alignment gate.
- Короткое ожидаемое поведение: one migration owner upgrades schema, API/worker wait for it, tests gate deploy, and smoke identifies frontend/API/worker/schema versions.

## Фактическое поведение и воспроизведение

- Static steps: push main → production deploy starts directly → API image runs `alembic upgrade head`; worker separately runs the same command after only `service_started` dependency.
- Visible effect: deploy smoke passes on `/`, `/seller/`, `/api/health` HTTP 200 even if worker/schema/frontend versions differ.
- Repeatability: static `1/1`; no deployment was invoked.

## Доказательства

- code path: `.github/workflows/ci.yml:1-6` says CI is optional PR-only; `deploy.yml:1-7,35-44` deploys main without CI and performs only status checks; `backend/Dockerfile:21`, `Dockerfile.railway:18`, `docker-compose.prod.yml:26-69` make API and worker migration runners.
- migration tests: PostgreSQL round-trip skips without `WMS_TEST_DATABASE_URL`; default pytest/Playwright use SQLite/create-all.
- corroboration: reachable commit `8097bc089e9a92c4053ddda619282edd57bacd78` is titled “one service applies migrations; others wait for schema”, but it is not in etalon.

## Ущерб и граница

- Кто страдает: every deployment and background consumer.
- Результат: intermittent migration collision, worker/API schema mismatch, false-green release.
- Workaround: manually serialize startup and inspect component/schema versions.
- Почему дефект: atomic deploy alignment is an existing operational requirement.
- Не входит: merging the later hotfix or changing hosting provider.

## Анализ причины

- Proven root cause: deployment graph has multiple migration owners and no version-aware readiness gate.
- Retry/recovery: a restart can repeat migration competition; simple health remains green.
- Tenant implications: shared schema failure affects all tenants.

## Критерий закрытия

- Given: a migration-bearing release
- When: deployment starts API, worker and beat concurrently
- Then: exactly one owner upgrades; consumers start only at expected head
- And: CI plus smoke assert exact frontend/API/worker SHA and schema revision

## Вердикт оркестратора

- Accepted: `STATIC RISK`; runtime closure pending
- Second reproduction: static configuration independently confirmed; controlled deploy test still required
- Queue status: P1 static release risk; controlled deploy closure pending

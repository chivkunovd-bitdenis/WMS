# TL-F005 — Фоновая операция может навсегда остаться pending/running после сбоя доставки или worker

## Паспорт

- Finding ID: `TL-F005`
- Title: accepted background sync can remain permanently pending or running with no automatic recovery
- Class: `RELIABILITY`
- Severity: P1
- Area / scenario ID: background jobs / failure recovery
- First reviewer / independent verifier: teamlead / pending runtime fault injection
- Environment and SHA: `a39530c`
- WB mode: test/emulator required for closure; none used here

## Ожидаемое поведение

- Источник правды: API returns `202 Accepted`; review charter requires retry/recovery and no false success.
- Короткое ожидаемое поведение: accepted work is durably delivered, or enqueue/worker loss becomes a terminal/retryable state visible to the user.

## Фактическое поведение и воспроизведение

- Static sequence A: `create_pending_job` commits pending, then API calls `.delay`; broker failure occurs after the commit and no compensating status is written.
- Static sequence B: worker commits running before work; worker death thereafter leaves running.
- User/data effect: polling returns a non-terminal state indefinitely; rerun identity is not defined for generic jobs.
- Repeatability: static `1/1`; no staging worker fault injection authorized.

## Доказательства

- code path: `background_job_service.py:32-48,62-95,98-146`; `api/background_jobs.py:84-92,107-116,131-140,155-164,199-208`; task wrappers `tasks/background_jobs.py:18-40` have no `acks_late`, retry policy or recovery sweep; `celery_app.py:10-37` defines schedules but no stale-job reconciliation.
- tests: `backend/tests/test_background_jobs.py` covers normal start/read, not broker publish loss or worker death.

## Ущерб и граница

- Кто страдает: operators launching catalog/supply/order sync or movement digest.
- Результат: false accepted state, stale external data, manual uncertainty and duplicate reruns.
- Workaround: inspect infrastructure and manually recreate work; no UI repair action is established.
- Почему дефект: 202 promises accepted asynchronous processing, not an unrecoverable limbo.
- Не входит: FBS WB-operation reconciliation, which has separate durable operation records.

## Анализ причины

- Proven root cause: DB state transition and queue publication are separate effects, and running jobs have no lease/heartbeat/reaper.
- Retry implications: blind manual retry can duplicate non-idempotent work; generic task delivery is not late-acknowledged.
- Tenant implications: job reads are tenant-filtered, but recovery absence affects each tenant independently.

## Критерий закрытия

- Given: broker publish failure or worker death after running commit
- When: operator reads the job after a bounded interval
- Then: it is retried/reconciled or terminal with a clear recoverable error
- And: retry preserves one business effect

## Вердикт оркестратора

- Accepted: `STATIC RISK`; runtime closure pending
- Second reproduction: required for P1
- Queue status: P1 static risk, not a runtime-confirmed outage

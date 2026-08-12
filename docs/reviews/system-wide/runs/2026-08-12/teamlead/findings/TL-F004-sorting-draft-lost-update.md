# TL-F004 — Два сортировщика могут стереть размещение друг друга

## Паспорт

- Finding ID: `TL-F004`
- Title: concurrent loose putaway replaces the whole distribution draft, so the later writer can erase the earlier writer's placement
- Class: `RELIABILITY`
- Severity: P1
- Area / scenario ID: inbound sorting / mobile concurrency
- First reviewer / independent verifier: teamlead / pending runtime reproduction
- Environment and SHA: backend `a39530c`; mobile `09aa479f`
- Role / tenant / seller test IDs: N/A
- WB mode: N/A

## Ожидаемое поведение

- Источник правды: review charter quantity conservation and multi-operator concurrency requirement.
- Короткое ожидаемое поведение: independent scans by two sorters are merged or one receives a conflict; neither successful response erases another placement.

## Фактическое поведение и воспроизведение

- Preconditions: one request in sorting, two clients with the same initial distribution list.
- Static steps: both GET list → each merges its own line → both PUT the full list.
- User-visible/data effect: both can receive success, while the last full replacement deletes the first writer's lines.
- Repeatability: deterministic control-flow proof; staging concurrency not run.

## Доказательства

- code path: mobile `SortingViewModel.kt:161-195` explicitly describes and only narrows the GET+PUT race; backend `inbound_intake_service.py:1041-1119` deletes every row then inserts the submitted list without version/row lock.
- existing automated test: no two-writer distribution replacement test found; local tests not run.

## Ущерб и граница

- Кто страдает: warehouses sorting one intake on multiple devices.
- Результат: stored location plan loses accepted units or points to stale locations; completion may block or encode an incomplete draft.
- Workaround: serialize sorting per inbound request and reload before every scan.
- Почему дефект: multi-operator work must not lose acknowledged input.
- Не входит: concurrent complete-receiving (`TL-F001`).

## Анализ причины

- Proven root cause: full-list last-write-wins contract without compare-and-swap or atomic increment.
- Recovery implications: reload cannot reconstruct the erased placement from the distribution table.
- Tenant/seller implications: scoped to the request tenant, but damages its authoritative placement state.

## Критерий закрытия

- Given: two clients starting from the same distribution version
- When: they add distinct placements concurrently
- Then: both placements persist, or one receives an explicit stale-version conflict
- And: quantity totals stay conserved after reload and completion

## Вердикт оркестратора

- Accepted: `STATIC RISK`; runtime closure pending
- Second reproduction for P0/P1: required
- Queue status: P1 static risk, not a runtime-confirmed defect

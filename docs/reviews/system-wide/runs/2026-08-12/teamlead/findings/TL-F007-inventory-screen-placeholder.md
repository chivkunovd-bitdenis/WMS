# TL-F007 — Раздел «Инвентаризация» не содержит ни одной инвентаризационной операции

## Паспорт

- Finding ID: `TL-F007`
- Title: operator opens Inventory and receives only “section under development”
- Class: `PRODUCT_GAP`
- Severity: P2
- Area / scenario ID: TL-INV-01
- First reviewer / independent verifier: orchestrator execution / teamlead visual adjudication
- Environment and SHA: staging, deployed SHA attribution blocked
- Role / tenant / seller test IDs: synthetic administrator
- WB mode: N/A

## Ожидаемое поведение

- Источник правды: named FF navigation route and mandatory review inventory-mutation path.
- Короткое ожидаемое поведение: operator can start/read an inventory count or correction workflow.

## Фактическое поведение и воспроизведение

- Steps: sign in as admin → click Inventory → wait stable.
- User-visible: only `Раздел в разработке`.
- Data effect: no mutation is available.
- Repeatability: visible at 1280 and stable 1920 (`2/2`).

## Доказательства

- screenshots: `UI-FF-INVENTORY__synthetic-admin__1280x720__clicked.png` and `...1920x1080__stable-2s.png`, hashes in `ui-evidence/index.md`.
- reload/state proof: no operation exists to read back; route render only.
- code path: frontend route is a placeholder; UI evidence is authoritative for the user-visible claim.
- tests: no end-to-end inventory mutation was supplied.

## Ущерб и граница

- Кто страдает: FF operators reconciling physical and system stock.
- Результат: workflow dead end and external/manual inventory correction.
- Workaround: use unrelated stock APIs/other screens outside the named route; this is not an equivalent operator flow.
- Почему дефект: navigation advertises the capability.
- Не входит: inventing a new inventory model or UX.

## Критерий закрытия

- Given: stock and a permitted warehouse role
- When: operator completes one count/correction
- Then: visible result survives reload
- And: movement/balance audit trail matches exactly once with tenant isolation

## Вердикт оркестратора

- Accepted: pending
- Queue status: proposed P2

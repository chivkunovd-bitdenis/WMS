# TC automation coverage (Playwright e2e)

- Catalog: `docs/IMPLEMENTED_PRODUCT_SCENARIOS_TEST_CASES_EN.md` (61 TC headings)
- Covered by e2e (TC mentioned in `frontend/tests-e2e/*.spec.ts`): 12/61

## Coverage table

| TC-ID | Title | Automated (e2e) | Specs |
|------|-------|------------------|-------|
| `TC-S01-001` | Successful first-time registration (admin) | Y | `auth.spec.ts` |
| `TC-S01-002` | Registration rejected — duplicate or invalid slug / email | Y | `auth-core.spec.ts` |
| `TC-S02-001` | Successful login | Y | `admin-shell-layout.spec.ts` |
| `TC-S02-002` | Login failure — wrong password | Y | `auth-core.spec.ts` |
| `TC-S02-003` | Logout | Y | `auth-core.spec.ts` |
| `TC-S03-001` | Admin creates warehouse | N |  |
| `TC-S03-002` | Admin creates locations (cells) under a warehouse | N |  |
| `TC-S03-003` | Seller cannot manage warehouses in current UI | N |  |
| `TC-S03-004` | Conceptual dependency — locations needed for some flows | N |  |
| `TC-S04-001` | Admin creates seller record | N |  |
| `TC-S04-002` | Seller user is not created automatically with seller record | N |  |
| `TC-S05-001` | Admin creates product with required fields | N |  |
| `TC-S05-002` | After WB link — product list shows WB identifiers (when linked) | N |  |
| `TC-S05-003` | Seller cannot use admin “create product” form | N |  |
| `TC-S05-004` | Seller sees only allowed products | N |  |
| `TC-S06-001` | Create inbound request (draft) — choose warehouse | N |  |
| `TC-S06-002` | Add inbound line — product and expected quantity | N |  |
| `TC-S06-003` | Duplicate product line on same inbound rejected | N |  |
| `TC-S06-004` | Submit inbound request | N |  |
| `TC-S06-005` | Assign or change storage cell on line (when status allows) | N |  |
| `TC-S06-006` | Receive partial quantity on line | N |  |
| `TC-S06-007` | Post inbound — inventory and movements | N |  |
| `TC-S06-008` | Seller restricted on post / some warehouse actions | N |  |
| `TC-S07-001` | Successful transfer within same warehouse | N |  |
| `TC-S07-002` | Transfer rejected — exceeds available (incl. reservation effect) | N |  |
| `TC-S07-003` | Transfer rejected — different warehouses | N |  |
| `TC-S07-004` | Seller cannot perform stock transfer | N |  |
| `TC-S08-001` | Create outbound draft — choose warehouse | N |  |
| `TC-S08-002` | Add outbound line — product, quantity, optional pick location | N |  |
| `TC-S08-003` | Duplicate SKU line on same outbound rejected | N |  |
| `TC-S08-004` | Mixed sellers on one outbound rejected | N |  |
| `TC-S08-005` | Submit outbound — reservations revalidated | Y | `outbound-reservation.spec.ts` |
| `TC-S08-006` | Ship partial quantity (admin) | N |  |
| `TC-S08-007` | Post remaining unshipped quantity (admin) | N |  |
| `TC-S08-008` | Fully shipped — request posted / closed | N |  |
| `TC-S08-009` | Seller cannot ship or post outbound | N |  |
| `TC-S09-001` | Balances show on hand, reserved, available (where exposed) | N |  |
| `TC-S09-002` | Second outbound cannot reserve beyond available | Y | `outbound-reservation.spec.ts` |
| `TC-S09-003` | Transfer limited by available when outbound reserves stock | Y | `outbound-reservation.spec.ts` |
| `TC-S09-004` | Reservation released on ship, draft line delete, or line closure | Y | `outbound-delete-line.spec.ts` |
| `TC-S10-001` | Admin deletes line on draft outbound | Y | `outbound-delete-line.spec.ts` |
| `TC-S10-002` | Cannot delete line when not draft | N |  |
| `TC-S11-001` | Prerequisites — seller exists before integration | N |  |
| `TC-S11-002` | Save tokens — secrets not shown in UI | N |  |
| `TC-S11-003` | Sync product cards — async job with summary | N |  |
| `TC-S11-004` | Sync FBW supplies — async job with summary | N |  |
| `TC-S11-005` | View imported cards and supplies lists | N |  |
| `TC-S11-006` | Link internal SKU to WB nm_id (same seller rules) | N |  |
| `TC-S11-007` | MVP boundaries — no create WB card/supply from app | N |  |
| `TC-S12-001` | Admin creates seller account bound to seller | N |  |
| `TC-S12-002` | Seller login — dashboard shows seller context | N |  |
| `TC-S12-003` | Seller sees filtered lists only for their seller | N |  |
| `TC-S12-004` | Seller draft inbound/outbound within UI allowance | N |  |
| `TC-S13-001` | Global movements list — refresh | N |  |
| `TC-S13-002` | Movements on selected inbound / outbound | N |  |
| `TC-S13-003` | Admin vs seller visibility | N |  |
| `TC-S14-001` | Movements digest job lifecycle | N |  |
| `TC-S14-002` | WB sync jobs lifecycle | N |  |
| `TC-S14-003` | Environment boundary (informational for test design) | N |  |
| `TC-S15-001` | Section navigation after login | Y | `admin-shell-layout.spec.ts`, `auth-core.spec.ts`, `auth.spec.ts` |
| `TC-S15-002` | Profile loading state | Y | `auth-core.spec.ts` |

## Gaps (not yet automated)

- `TC-S03-001` — Admin creates warehouse
- `TC-S03-002` — Admin creates locations (cells) under a warehouse
- `TC-S03-003` — Seller cannot manage warehouses in current UI
- `TC-S03-004` — Conceptual dependency — locations needed for some flows
- `TC-S04-001` — Admin creates seller record
- `TC-S04-002` — Seller user is not created automatically with seller record
- `TC-S05-001` — Admin creates product with required fields
- `TC-S05-002` — After WB link — product list shows WB identifiers (when linked)
- `TC-S05-003` — Seller cannot use admin “create product” form
- `TC-S05-004` — Seller sees only allowed products
- `TC-S06-001` — Create inbound request (draft) — choose warehouse
- `TC-S06-002` — Add inbound line — product and expected quantity
- `TC-S06-003` — Duplicate product line on same inbound rejected
- `TC-S06-004` — Submit inbound request
- `TC-S06-005` — Assign or change storage cell on line (when status allows)
- `TC-S06-006` — Receive partial quantity on line
- `TC-S06-007` — Post inbound — inventory and movements
- `TC-S06-008` — Seller restricted on post / some warehouse actions
- `TC-S07-001` — Successful transfer within same warehouse
- `TC-S07-002` — Transfer rejected — exceeds available (incl. reservation effect)
- `TC-S07-003` — Transfer rejected — different warehouses
- `TC-S07-004` — Seller cannot perform stock transfer
- `TC-S08-001` — Create outbound draft — choose warehouse
- `TC-S08-002` — Add outbound line — product, quantity, optional pick location
- `TC-S08-003` — Duplicate SKU line on same outbound rejected
- `TC-S08-004` — Mixed sellers on one outbound rejected
- `TC-S08-006` — Ship partial quantity (admin)
- `TC-S08-007` — Post remaining unshipped quantity (admin)
- `TC-S08-008` — Fully shipped — request posted / closed
- `TC-S08-009` — Seller cannot ship or post outbound
- `TC-S09-001` — Balances show on hand, reserved, available (where exposed)
- `TC-S10-002` — Cannot delete line when not draft
- `TC-S11-001` — Prerequisites — seller exists before integration
- `TC-S11-002` — Save tokens — secrets not shown in UI
- `TC-S11-003` — Sync product cards — async job with summary
- `TC-S11-004` — Sync FBW supplies — async job with summary
- `TC-S11-005` — View imported cards and supplies lists
- `TC-S11-006` — Link internal SKU to WB nm_id (same seller rules)
- `TC-S11-007` — MVP boundaries — no create WB card/supply from app
- `TC-S12-001` — Admin creates seller account bound to seller
- `TC-S12-002` — Seller login — dashboard shows seller context
- `TC-S12-003` — Seller sees filtered lists only for their seller
- `TC-S12-004` — Seller draft inbound/outbound within UI allowance
- `TC-S13-001` — Global movements list — refresh
- `TC-S13-002` — Movements on selected inbound / outbound
- `TC-S13-003` — Admin vs seller visibility
- `TC-S14-001` — Movements digest job lifecycle
- `TC-S14-002` — WB sync jobs lifecycle
- `TC-S14-003` — Environment boundary (informational for test design)

## Notes

- This report is a *traceability map*, not a proof of correctness.
- A TC is considered automated if its ID is mentioned in a Playwright spec (title or comment).

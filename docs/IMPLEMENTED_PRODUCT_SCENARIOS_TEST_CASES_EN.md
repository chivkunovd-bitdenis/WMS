# Test cases derived from implemented product scenarios (business-only)

This document expands **[IMPLEMENTED_PRODUCT_SCENARIOS_EN.md](./IMPLEMENTED_PRODUCT_SCENARIOS_EN.md)** into **manual / future automation** test cases. It describes **expected behaviour, user capabilities, and restrictions** as stated in that scenario document only — **not** implementation details, API contracts, or selectors.

**How to use**

- Each case has a stable **ID** (`TC-Sxx-yyy`) for traceability to scenario sections (S01 = §1, …).
- **Preconditions** state what must exist before the test (tenant, role, data).
- **Steps** are user-visible actions (forms, navigation, confirmations).
- **Expected** is observable outcome (screens, lists, messages, disabled actions).
- **Negative / restrictions** lists what the user must **not** be able to do or what error UX is expected when the scenario document calls for it.

**Roles** (from scenarios): **Fulfillment admin**, **Fulfillment seller**. **Tenant** = one organization; data isolated per tenant.

---

## S01 — Registration and first access

### TC-S01-001 Successful first-time registration (admin)

- **Actor:** new user with no prior account (intended admin).
- **Preconditions:** none (or use unique email/slug not already taken).
- **Steps:**
  1. Open the public registration experience.
  2. Enter organization name, URL slug (Latin), admin email, password.
  3. Submit registration (primary action to complete sign-up).
- **Expected:**
  - System creates the tenant and establishes a logged-in session.
  - User lands on the **dashboard** showing at least: email, organization name, role.
  - User can reach **catalog** and **operations** areas (via navigation described in S15).
- **Negative / restrictions:** n/a for happy path.

### TC-S01-002 Registration rejected — duplicate or invalid slug / email

- **Actor:** new user.
- **Preconditions:** slug and/or email already used by another tenant, **or** slug weak/invalid per product rules.
- **Steps:** same as TC-S01-001 with conflicting or invalid slug/email.
- **Expected:**
  - Registration does not complete as a new tenant for the conflicting case.
  - User receives a **clear** validation or error message (not silent failure).
- **Negative / restrictions:** user must not gain access to another tenant’s data.

---

## S02 — Login and logout

### TC-S02-001 Successful login

- **Actor:** any user with valid credentials.
- **Preconditions:** account exists.
- **Steps:**
  1. Open login.
  2. Enter email and password.
  3. Submit login.
- **Expected:**
  - Session/token issued; same post-login experience as after registration (profile + catalog/operations access per role).

### TC-S02-002 Login failure — wrong password

- **Actor:** user with existing email.
- **Preconditions:** known wrong password.
- **Steps:** submit login with wrong password.
- **Expected:**
  - Error shown; **no** access to authenticated areas or other tenants’ data.

### TC-S02-003 Logout

- **Actor:** logged-in user.
- **Preconditions:** active session.
- **Steps:** invoke **logout** (user-initiated sign-out control).
- **Expected:**
  - Session cleared **client-side** as described; user returned to **public** login/registration screen.

---

## S03 — Warehouses and storage locations

### TC-S03-001 Admin creates warehouse

- **Actor:** fulfillment admin.
- **Preconditions:** logged-in admin.
- **Steps:**
  1. Navigate to warehouse management (admin-only catalog/warehouse UI).
  2. Create a **warehouse** with name and code.
- **Expected:** warehouse appears in the admin’s list and is selectable for further actions.

### TC-S03-002 Admin creates locations (cells) under a warehouse

- **Actor:** fulfillment admin.
- **Preconditions:** at least one warehouse exists.
- **Steps:**
  1. Select a warehouse.
  2. Create one or more **locations** (cell codes).
- **Expected:** locations exist as atomic places for stock and for inbound/outbound line assignment (per scenario).

### TC-S03-003 Seller cannot manage warehouses in current UI

- **Actor:** fulfillment seller.
- **Preconditions:** seller account logged in.
- **Steps:** attempt to find and use warehouse/location **creation** flows available to admin.
- **Expected:**
  - Per scenario: seller **does not** manage warehouses in the current UI — no equivalent admin capability exposed, or actions unavailable/disabled/hidden.

### TC-S03-004 Conceptual dependency — locations needed for some flows

- **Actor:** admin (and later seller where applicable).
- **Preconditions:** warehouse exists but **no** locations (or insufficient for a flow).
- **Steps:** attempt inbound/outbound flows that the scenario says require locations first.
- **Expected:** user is guided or blocked until locations exist (exact copy is product-specific; assert non-success without locations).

---

## S04 — Sellers (B2B clients)

### TC-S04-001 Admin creates seller record

- **Actor:** fulfillment admin.
- **Preconditions:** tenant exists.
- **Steps:** create a **seller** record (name).
- **Expected:** seller exists for grouping, future seller users, and WB integration (per seller).

### TC-S04-002 Seller user is not created automatically with seller record

- **Actor:** admin.
- **Preconditions:** seller record created.
- **Steps:** confirm there is no automatic seller login until **seller account** is created per S12.
- **Expected:** scenario boundary: seller accounts are **separate** from seller records.

---

## S05 — Products (SKU)

### TC-S05-001 Admin creates product with required fields

- **Actor:** fulfillment admin.
- **Preconditions:** admin logged in (seller optional for attach step).
- **Steps:**
  1. Open product creation (admin form).
  2. Enter name, SKU code, dimensions (length / width / height in mm).
  3. Optionally attach **seller** (owner).
  4. Save / submit product.
- **Expected:**
  - Product stored and visible in **product list**.
  - Where applicable, **volume** is shown or derivable in UI (computed display per scenario).

### TC-S05-002 After WB link — product list shows WB identifiers (when linked)

- **Actor:** admin.
- **Preconditions:** product exists; WB link performed per S11 for same seller as product rules allow.
- **Steps:** open product list / product row.
- **Expected:** product may show **WB nmID** and **vendor code** in list (per scenario).

### TC-S05-003 Seller cannot use admin “create product” form

- **Actor:** fulfillment seller.
- **Preconditions:** seller logged in.
- **Steps:** attempt to access or submit the admin product creation flow.
- **Expected:** not available in current UI (hidden, disabled, or access denied).

### TC-S05-004 Seller sees only allowed products

- **Actor:** fulfillment seller.
- **Preconditions:** products exist for multiple sellers and/or unscoped; seller linked to one seller.
- **Steps:** open product listing as seller.
- **Expected:** only products **owned by / scoped to** that seller (or per “unscoped product rules in UI”); no other tenant seller’s catalog.

---

## S06 — Inbound intake (receiving)

### TC-S06-001 Create inbound request (draft) — choose warehouse

- **Actor:** admin or seller (where UI allows creation).
- **Preconditions:** warehouse exists; user has permission to start inbound.
- **Steps:** create inbound **request** and select **warehouse**.
- **Expected:** **draft** inbound request exists.

### TC-S06-002 Add inbound line — product and expected quantity

- **Actor:** admin or seller (where allowed).
- **Preconditions:** draft inbound open; product exists and selectable for this actor.
- **Steps:** add line: product, expected quantity; optionally set **storage location** now or leave for later.
- **Expected:** line appears on request; quantity and product shown correctly.

### TC-S06-003 Duplicate product line on same inbound rejected

- **Actor:** admin or seller.
- **Preconditions:** draft inbound with a line for product P.
- **Steps:** add second line for the **same** product P on the **same** request.
- **Expected:** not allowed — clear prevention or error (scenario: duplicate line not allowed).

### TC-S06-004 Submit inbound request

- **Actor:** admin or seller (where allowed).
- **Preconditions:** draft with valid lines.
- **Steps:** **submit** request.
- **Expected:** request moves to **submitted** state suitable for warehouse processing.

### TC-S06-005 Assign or change storage cell on line (when status allows)

- **Actor:** typically admin for warehouse execution (seller may be read-only on some actions).
- **Preconditions:** submitted (or draft, per rules) inbound; line may lack cell.
- **Steps:** assign or change **cell** on line when UI allows for status.
- **Expected:** line shows updated location; operation succeeds when permitted.

### TC-S06-006 Receive partial quantity on line

- **Actor:** admin (seller limited per scenario on critical steps).
- **Preconditions:** inbound in receivable state with line and location as required by app rules.
- **Steps:** record **receive** for **part** of expected quantity.
- **Expected:** received quantity accumulates; partial allowed.

### TC-S06-007 Post inbound — inventory and movements

- **Actor:** admin (seller read-only on post per scenario/UI).
- **Preconditions:** inbound ready for post per product rules; lines have assignments as required.
- **Steps:** execute **post** (finalize unreceived remainder per app rules).
- **Expected:**
  - **Inventory increases** in assigned locations as per implemented rules.
  - **Movements** visible in relevant journals.
  - Optional: **per-location balances** snippet for affected cells (admin view).

### TC-S06-008 Seller restricted on post / some warehouse actions

- **Actor:** seller.
- **Preconditions:** inbound exists where admin could post.
- **Steps:** attempt **post** and other critical warehouse actions on inbound.
- **Expected:** seller **cannot** complete those actions where UI restricts; fulfillment executes critical steps.

---

## S07 — Stock transfer (between locations)

### TC-S07-001 Successful transfer within same warehouse

- **Actor:** fulfillment admin.
- **Preconditions:** two locations in same warehouse; product has sufficient **available** in source cell.
- **Steps:**
  1. Open transfer flow.
  2. Choose **from** location, **to** location, product, quantity.
  3. Confirm transfer.
- **Expected:**
  - Source decreases; destination increases by same quantity.
  - **Transfer** movements recorded; **total** tenant stock unchanged.

### TC-S07-002 Transfer rejected — exceeds available (incl. reservation effect)

- **Actor:** admin.
- **Preconditions:** source cell has on-hand stock but **available** is lower due to **reserved** outbound (S09).
- **Steps:** attempt transfer quantity **greater than available**.
- **Expected:** operation rejected or capped per rules; user informed.

### TC-S07-003 Transfer rejected — different warehouses

- **Actor:** admin.
- **Preconditions:** from and to in different warehouses.
- **Steps:** attempt cross-warehouse transfer in this flow.
- **Expected:** not allowed in this flow (scenario boundary).

### TC-S07-004 Seller cannot perform stock transfer

- **Actor:** seller.
- **Preconditions:** seller logged in.
- **Steps:** attempt transfer UI/actions.
- **Expected:** not available in current UI.

---

## S08 — Outbound shipment (picking / shipping)

### TC-S08-001 Create outbound draft — choose warehouse

- **Actor:** admin or seller (draft creation where allowed).
- **Preconditions:** warehouse exists.
- **Steps:** create **outbound request**; select warehouse.
- **Expected:** **draft** outbound exists; may inherit **seller** from first line (per scenario).

### TC-S08-002 Add outbound line — product, quantity, optional pick location

- **Actor:** admin or seller (where allowed).
- **Preconditions:** draft outbound; product selectable; stock rules satisfied when location assigned.
- **Steps:** add line with product, quantity; optionally assign **pick location** (cell).
- **Expected:** line on request; when location present in draft/submitted states, **reservation** applies to **available** (see S09).

### TC-S08-003 Duplicate SKU line on same outbound rejected

- **Preconditions:** draft outbound with line for product P.
- **Steps:** add another line for same P.
- **Expected:** rejected (one line per product per request).

### TC-S08-004 Mixed sellers on one outbound rejected

- **Preconditions:** lines would belong to different sellers.
- **Steps:** combine incompatible lines on one outbound.
- **Expected:** rejected.

### TC-S08-005 Submit outbound — reservations revalidated

- **Actor:** admin or seller (submit where allowed).
- **Preconditions:** draft with valid lines and stock/reservation rules met.
- **Steps:** **submit** outbound.
- **Expected:** submitted state; reservations **revalidated**.

### TC-S08-006 Ship partial quantity (admin)

- **Actor:** fulfillment admin.
- **Preconditions:** submitted outbound with shippable lines.
- **Steps:** **ship partial** quantity on a line.
- **Expected:** stock decreases; shipped quantity updates; **reservation shrinks** accordingly.

### TC-S08-007 Post remaining unshipped quantity (admin)

- **Actor:** admin.
- **Preconditions:** lines with storage assigned; remaining unshipped quantity exists per rules.
- **Steps:** **post remaining**.
- **Expected:** all still-unshipped quantity on eligible lines is shipped per scenario; movements tie to outbound lines.

### TC-S08-008 Fully shipped — request posted / closed

- **Preconditions:** outbound fully shipped per line rules.
- **Expected:** request **posted** (closed for further shipping).

### TC-S08-009 Seller cannot ship or post outbound

- **Actor:** seller.
- **Preconditions:** outbound exists that admin could ship/post.
- **Steps:** attempt ship/post controls.
- **Expected:** seller **cannot** ship lines or post in current UI.

---

## S09 — Reservation and “available” stock

### TC-S09-001 Balances show on hand, reserved, available (where exposed)

- **Actor:** admin (and seller where API/UI exposes balances per visibility).
- **Preconditions:** stock in cell; optional active outbound reservations.
- **Steps:** open balance display (global or contextual, e.g. after inbound post hints).
- **Expected:** user can see **on hand**, **reserved**, **available** as product exposes them.

### TC-S09-002 Second outbound cannot reserve beyond available

- **Preconditions:** outbound A reserves most of cell C’s stock; outbound B targets same cell.
- **Steps:** outbound B tries to reserve quantity exceeding **available** in C.
- **Expected:** prevention or clear failure; no over-reservation.

### TC-S09-003 Transfer limited by available when outbound reserves stock

- **Preconditions:** outbound reserves stock in cell C.
- **Steps:** attempt transfer from C for quantity **> available**.
- **Expected:** cannot transfer more than **available** (S07 alignment).

### TC-S09-004 Reservation released on ship, draft line delete, or line closure

- **Preconditions:** draft outbound line with reservation, or submitted line with partial ship.
- **Steps:** (a) ship quantity; (b) admin deletes **draft** line (S10); (c) post/close until zero reserved.
- **Expected:** reserved amount decreases or clears per scenario rules; stock freed for other orders/transfers.

---

## S10 — Delete outbound line (draft)

### TC-S10-001 Admin deletes line on draft outbound

- **Actor:** fulfillment admin.
- **Preconditions:** **draft** outbound with at least one line.
- **Steps:** delete a line (explicit delete control).
- **Expected:**
  - Line removed from UI/list.
  - Reservation for that line **gone**.
  - If last line removed: **seller linkage** on request may **reset** (per scenario).

### TC-S10-002 Cannot delete line when not draft

- **Actor:** admin.
- **Preconditions:** outbound in **submitted** or **posted** state.
- **Steps:** attempt delete line.
- **Expected:** not allowed; user must use normal shipping flows (scenario boundary).

---

## S11 — Wildberries import (read-only integration)

### TC-S11-001 Prerequisites — seller exists before integration

- **Actor:** admin.
- **Preconditions:** no seller vs seller exists.
- **Steps:** attempt WB integration seller selection / token save without seller.
- **Expected:** at least one **seller** required; integration is **per seller**.

### TC-S11-002 Save tokens — secrets not shown in UI

- **Actor:** admin.
- **Preconditions:** seller selected; valid-format tokens from outside WB cabinet (test or real per environment).
- **Steps:** paste/save tokens via **save tokens** action.
- **Expected:**
  - Tokens stored server-side encrypted (not verifiable in UI beyond behaviour).
  - UI shows **flags** such as “has token”, **not** raw secrets.

### TC-S11-003 Sync product cards — async job with summary

- **Steps:** start **sync product cards** (first page scope per MVP).
- **Expected:** background job pattern: start → wait/poll until **done/failed** → **short text summary** visible.

### TC-S11-004 Sync FBW supplies — async job with summary

- **Same pattern as TC-S11-003** for supplies sync.

### TC-S11-005 View imported cards and supplies lists

- **Steps:** open **imported cards** and **imported supplies** lists after sync.
- **Expected:** snapshot data visible in UI (DB-backed lists per scenario).

### TC-S11-006 Link internal SKU to WB nm_id (same seller rules)

- **Preconditions:** internal product and imported card for **same seller** as linking rules require.
- **Steps:** perform **link SKU** to **nm_id** (and vendor code rules as product defines).
- **Expected:** link reflected; product list may show WB fields (see TC-S05-002).

### TC-S11-007 MVP boundaries — no create WB card/supply from app

- **Steps:** look for actions to **create** WB catalog cards or WB supplies from this product.
- **Expected:** **not** present — import/read-only MVP; no pagination/extra fields/label print in this slice (scenario says not in slice — assert absence or disabled marketing).

---

## S12 — Seller user account and seller “cabinet”

### TC-S12-001 Admin creates seller account bound to seller

- **Actor:** admin.
- **Preconditions:** seller record exists.
- **Steps:** create **seller account** (email + password) linked to that seller.
- **Expected:** account can log in as seller role/context.

### TC-S12-002 Seller login — dashboard shows seller context

- **Actor:** seller.
- **Steps:** log in with seller credentials.
- **Expected:** dashboard reflects **seller** context (not full-tenant admin view).

### TC-S12-003 Seller sees filtered lists only for their seller

- **Steps:** open products, inbound/outbound summaries, movements, balances.
- **Expected:** only data belonging to **that seller** per backend visibility rules; no other sellers’ data.

### TC-S12-004 Seller draft inbound/outbound within UI allowance

- **Steps:** create **draft** inbound/outbound for own assortment where UI allows.
- **Expected:** drafts created; **sensitive fulfillment** actions remain unavailable on seller side where restricted (align with S06/S08 matrix).

---

## S13 — Global movements and outbound movement list

### TC-S13-001 Global movements list — refresh

- **Actor:** any logged-in user within visibility.
- **Steps:** open **global movements**; trigger **refresh** if UI provides it.
- **Expected:** recent movements listed with types including inbound, transfer, outbound (within documented limits).

### TC-S13-002 Movements on selected inbound / outbound

- **Steps:** select a specific inbound or outbound request; open associated **movement list**.
- **Expected:** movements for that request visible (traceability within shown limits).

### TC-S13-003 Admin vs seller visibility

- **Preconditions:** tenant-wide vs seller-scoped movement data exists.
- **Steps:** compare admin view vs seller view.
- **Expected:** seller sees **seller-scoped** data; admin **tenant-wide** per summary table.

---

## S14 — Background jobs (generic + WB)

### TC-S14-001 Movements digest job lifecycle

- **Actor:** admin.
- **Steps:** start **movements digest** from exposed UI; wait until completion state.
- **Expected:** user sees lifecycle (not instant fake sync): polling or equivalent until **done/failed**; **short text result**.

### TC-S14-002 WB sync jobs lifecycle

- **Same expectations as TC-S14-001** for WB sync entry points (align with S11).

### TC-S14-003 Environment boundary (informational for test design)

- **Note:** With Celery vs without broker, execution may be worker vs inline/async per deployment — tests should assert **user-visible lifecycle**, not a specific infrastructure, unless environment is fixed.

---

## S15 — Navigation and layout (UX)

### TC-S15-001 Section navigation after login

- **Actor:** logged-in user.
- **Steps:** after login, use **section navigation** (anchors) to jump between **catalog** and **operations** on long single-page layout.
- **Expected:** focus/scroll lands on correct section; no broken navigation.

### TC-S15-002 Profile loading state

- **Steps:** load app while profile (`/auth/me` equivalent user journey) is loading.
- **Expected:** **loading** state visible; **no** overlapping login and register forms during load.

### TC-S15-003 Fulfillment admin dashboard — week planning and combined supplies/shipments

- **Actor:** fulfillment admin.
- **Preconditions:** logged-in session after registration or login (tenant exists).
- **Steps:**
  1. Land on the **fulfillment admin dashboard** (default post-auth landing for that shell).
  2. Confirm a **week-oriented planning** area is shown together with **short summaries** of supplies and shipments (may be empty for a new tenant).
  3. Use navigation to open **Supplies and shipments** (Russian UI: *Поставки и отгрузки*; unified list: seller→FC **supply**, operational outbound, **FC→marketplace shipment**, discrepancy acts — see `docs/MVP_DECISIONS_RU.md` terminology).
  4. On that page, use **Create shipment to MP** (Russian: *Создать отгрузку на МП*; backend `marketplace_unload`).
- **Expected:**
  - Week planning and document summary areas are **visible** and usable (e.g. change week if the UI offers it).
  - The combined list view opens without error; **Create shipment to MP** and **Create diverge** are visible; after create, a **success** notice appears and a draft row shows in the list (**Given/When/Then**).
  - Opening the FC→MP shipment row shows a line dialog; user can add a line and **confirm** the document (status «Утверждено» / confirmed).
- **Negative / restrictions:** without a warehouse, creating the FC→MP shipment should show a clear error; deeper inbound / operational outbound rules remain in S06/S08.

---

## Cross-scenario matrix (acceptance checklist for role tests)

Use this table as a **smoke checklist** when automating by role (from scenario summary; each cell should match at least one explicit case above).

| Area | Admin must be able to | Seller must be able to | Seller must not (current UI) |
|------|------------------------|-------------------------|------------------------------|
| Register tenant | Yes | N/A | Register as tenant creator if N/A |
| Warehouses / locations | Full management | — | Create warehouses/locations |
| Sellers & seller accounts | Create | — | Create |
| Products | Create, list all relevant | List filtered only | Use admin create product |
| Inbound | Full where UI allows | Draft/submit/receive per UI; not post where restricted | Post where restricted |
| Outbound | Full incl. delete draft line, submit, ship, post | Draft/lines where allowed | Submit/ship/post where restricted |
| Stock transfer | Yes | — | Transfer |
| WB tokens, sync, link | Yes | — | All WB integration |
| Movements / balances | Tenant-wide | Scoped view | See other sellers’ data |

---

## Document maintenance

Russian version (same `TC-*` IDs, wording aligned to **[IMPLEMENTED_PRODUCT_SCENARIOS_RU.md](./IMPLEMENTED_PRODUCT_SCENARIOS_RU.md)**): **[IMPLEMENTED_PRODUCT_SCENARIOS_TEST_CASES_RU.md](./IMPLEMENTED_PRODUCT_SCENARIOS_TEST_CASES_RU.md)**.

When **[IMPLEMENTED_PRODUCT_SCENARIOS_EN.md](./IMPLEMENTED_PRODUCT_SCENARIOS_EN.md)** changes, update this file so IDs and expectations stay aligned. For automation, map `TC-Sxx-yyy` to your test framework; add **selectors** (`data-testid`) in a separate layer once UI is fixed — this document intentionally stays business-level.

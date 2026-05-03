# Implemented product scenarios (business view)

This document describes **what is already built** from a user and process perspective: actors, steps, outcomes, and boundaries. It is not an API spec and not implementation detail.

**Roles**

- **Fulfillment admin** — tenant operator; full catalog and warehouse operations; can run WB integration UI; can submit/post inbound and outbound where the product allows; can create seller user accounts.
- **Fulfillment seller** — linked to one seller record; sees only data scoped to that seller; can create draft inbound/outbound for their products; cannot perform fulfillment-only actions (e.g. posting inbound, shipping outbound lines) where the UI restricts them.

**Multi-tenant model**

- Each registration creates a **tenant** (fulfillment organization). All data below is isolated per tenant.

---

## 1. Registration and first access

**Actor:** new fulfillment admin (no prior account).

**Flow**

1. User enters organization name, URL slug (latin), admin email, password.
2. System creates the tenant and logs the user in (session token).
3. User lands on the **dashboard** (email, organization name, role) and can navigate to **catalog** and **operations** sections.

**Outcomes**

- One organization = one tenant; admin is the first user.

**Boundaries**

- Slug and email uniqueness are enforced; weak or invalid slug rejected with a clear message.

---

## 2. Login and logout

**Actor:** any user with credentials.

**Flow**

1. User enters email and password → system validates → token issued.
2. User sees the same post-login experience as after registration (profile + sections).
3. **Logout** clears the session client-side; user returns to the public login/registration screen.

**Outcomes**

- Repeat visits: user can sign in without re-registering.

**Boundaries**

- Wrong password → error; no access to other tenants’ data.

---

## 3. Warehouses and storage locations

**Actor:** fulfillment admin only (seller does not manage warehouses in the current UI).

**Flow**

1. Admin creates a **warehouse** (name + code).
2. Admin selects a warehouse and creates **locations** (cell codes) within that warehouse.

**Outcomes**

- Locations are the atomic places where stock is tracked and where inbound/outbound lines point.

**Boundaries**

- Without at least one warehouse, location creation is not meaningful; without locations, some inbound/outbound flows require the user to add locations first.

---

## 4. Sellers (B2B clients)

**Actor:** fulfillment admin.

**Flow**

1. Admin creates **seller** records (name).
2. Optional: when creating a **product**, admin can attach it to a seller (owner).

**Outcomes**

- Sellers exist for commercial grouping and for **seller users** and **WB integration** (per seller).

**Boundaries**

- Seller user accounts are created separately (see §12).

---

## 5. Products (SKU)

**Actor:** fulfillment admin creates; fulfillment seller **sees** only products owned by their seller (or unscoped per product rules in UI).

**Flow**

1. Admin enters name, SKU code, dimensions (L/W/H in mm); optional seller.
2. System stores product and shows it in the product list (with computed volume where applicable).
3. After WB link (§11), product may show **WB nmID / vendor code** in the list.

**Outcomes**

- SKU is the unit of stock, reservations, and movements.

**Boundaries**

- Seller-scoped users cannot use the admin “create product” form in the current UI.

---

## 6. Inbound intake (receiving)

**Actor:** admin and seller can participate up to the limits below.

**Typical lifecycle**

1. **Create request** — choose warehouse → draft request exists.
2. **Add line** — choose product, expected quantity; optionally assign **storage location** immediately or later.
3. **Submit request** — moves to a submitted state suitable for warehouse processing.
4. **Assign / change cell** on a line (when allowed by status) if not set at creation.
5. **Receive quantity** on a line (partial allowed) — records received quantity toward the line.
6. **Post** — finalizes remaining unreceived quantity according to product rules in the app; **inventory increases** in the assigned locations; **movements** are visible in journals.

**Outcomes**

- Stock appears only after the flows that create positive movements (receive/post as implemented).
- After posting, the UI may show **per-location balances** snippet for affected cells (admin view).

**Boundaries**

- **Seller** may be read-only on posting / some warehouse actions depending on screen (fulfillment executes critical steps).
- Duplicate product line on the same inbound request is not allowed.

---

## 7. Stock transfer (between locations)

**Actor:** fulfillment admin.

**Flow**

1. Choose **from** location, **to** location (same warehouse), product, quantity.
2. System moves stock: decrement source, increment destination; writes **transfer movements**.

**Outcomes**

- Physical stock moves between cells without changing total tenant stock.

**Boundaries**

- Cannot transfer more than **available** quantity in the source cell (on hand minus **reserved** quantities tied to outbound lines — see §9).
- Cannot transfer between different warehouses in this flow.

---

## 8. Outbound shipment (picking / shipping)

**Actor:** admin drives execution; seller may create drafts and view where restricted.

**Lifecycle (conceptual)**

1. **Create outbound request** — choose warehouse; draft created (may inherit seller from first line).
2. **Add line** — product, quantity; optionally **pick location** (cell).
3. When a line has a **location in draft (or later submitted)**, the system **reserves** quantity (expected minus already shipped) against that cell’s **available** stock.
4. **Submit request** — moves to submitted; reservations are revalidated.
5. **Ship partial quantity** per line (admin) — decrements stock and updates shipped quantity; reservation shrinks accordingly.
6. **Post remaining** (admin) — ships all still-unshipped quantity on lines that have storage assigned.
7. When fully shipped, request becomes **posted** (closed for further shipping).

**Outcomes**

- Stock decreases on ship/post; movements reference outbound lines.
- **Reservation** prevents double-promising the same free stock to two outbound lines in the same cell.

**Boundaries**

- One line per product per outbound request (no duplicate SKU lines).
- Mixed sellers on one outbound request are rejected.
- **Seller** cannot ship lines or post in the current UI (fulfillment executes).

---

## 9. Reservation and “available” stock

**Business idea**

- **On hand** — physical quantity in a cell.
- **Reserved** — quantity promised to outbound lines (draft/submitted, with assigned cell, not yet fully shipped).
- **Available** — on hand minus reserved; used for **transfers** and for **adding outbound lines**.

**User-visible behavior**

- Balance API (and UI hints after inbound post) can show **reserved** and **available** alongside on hand.
- If outbound A reserves most of a cell, outbound B cannot reserve beyond **available**.
- If outbound blocks stock, **transfer** from that cell cannot take more than **available**.

**Release of reservation**

- Shipping reduces reserved amount; deleting a **draft** line (admin) removes its reservation; posting/closing lines clears reservation as quantities drop to zero.

---

## 10. Delete outbound line (draft)

**Actor:** fulfillment admin.

**Flow**

1. On a **draft** outbound request, admin deletes a line.
2. Line disappears; if it was the last line, seller linkage on the request may reset; reservation for that line is gone.

**Outcomes**

- Frees stock for other orders or transfers without forcing a fake shipment.

**Boundaries**

- Not allowed in **submitted** or **posted** states (must use normal shipping flows).

---

## 11. Wildberries import (read-only integration)

**Actor:** fulfillment admin.

**Prerequisites**

- At least one **seller** exists (integration is per seller).
- User obtains WB API tokens outside the app (WB personal cabinet / categories: Content, Supplies, etc.).

**Flow (high level)**

1. Select seller for integration.
2. **Save tokens** (stored encrypted server-side; UI shows only “has token” flags, not secrets).
3. **Sync product cards** (first page) — background job; result summary when done.
4. **Sync FBW supplies** (first page) — background job; result summary when done.
5. View **imported cards** and **imported supplies** lists (snapshots in DB).
6. **Link internal SKU** to a WB **nm_id** (and vendor code rules as implemented) for the same seller as the product.

**Outcomes**

- Tenant can mirror WB catalog/supply snapshots and tie internal SKU to WB identity.

**Boundaries (MVP)**

- **No** creation of WB cards or WB supplies from this product — import/read only.
- Pagination / extra fields / label print are **not** in this slice.
- In CI, WB HTTP is **mocked**; on a real server you need valid tokens and outbound network to WB (or your own mock).

---

## 12. Seller user account and seller “cabinet”

**Actor:** admin creates account; seller logs in with that email.

**Flow**

1. Admin creates **seller account** (email + password) bound to a seller.
2. Seller logs in → dashboard shows seller context.
3. Seller sees **filtered** lists: products, inbound/outbound summaries, movements, balances — only where data belongs to their seller (per backend rules).
4. Seller can create **draft** inbound/outbound for their assortment where the UI allows; sensitive fulfillment actions remain on admin side where restricted.

**Outcomes**

- Operational separation: seller self-service within scope; fulfillment retains control of execution steps as designed.

---

## 13. Global movements and outbound movement list

**Actor:** any logged-in user within their visibility rules.

**Flow**

- **Global movements** — refreshable list of recent stock movements (types such as inbound, transfer, outbound).
- **Per inbound / per outbound** — movement lists when a request is selected.

**Outcomes**

- Traceability of what changed stock and when (within shown limits).

---

## 14. Background jobs (generic + WB)

**Actor:** fulfillment admin for the exposed UI flows.

**Examples**

- **Movements digest** — heavy summary over movement log; user starts job, polls until **done/failed**, sees short text result.
- **WB sync jobs** — same pattern: start, wait for completion, read summary.

**Outcomes**

- Long work does not pretend to be synchronous; user sees lifecycle.

**Boundaries**

- With Celery configured, jobs run on workers; without broker (local/dev), equivalent **inline/async** execution may apply per deployment settings.

---

## 15. Navigation and layout (UX)

**After login**

- User sees **section navigation** (anchors) to jump to **catalog** vs **operations** on the long single-page layout.
- **Fulfillment admin** shell uses **sidebar + main content**: the default landing shows a **tenant dashboard** with a **week-oriented planning view** (planned **seller supplies** to the FC and planned **shipments** in the “scheduled” business sense) plus **shortlists** of recent documents; navigation includes **“Supplies and shipments”** (Russian: *Поставки и отгрузки*) that opens the unified list (including **FC→marketplace shipment** documents and **diverge** discrepancy acts). Russian product terms **поставка** vs **отгрузка на МП** are defined in `docs/MVP_DECISIONS_RU.md` (terminology section).
- While profile (`/auth/me`) is loading, user sees a **loading** state instead of overlapping login/register forms.

---

## Summary table (by actor)

| Area | Admin | Seller |
|------|-------|--------|
| Register tenant | Yes | N/A |
| Warehouses / locations | Yes | No (in current UI) |
| Create sellers & seller accounts | Yes | No |
| Create products | Yes | Read filtered |
| Inbound draft / submit / receive / post | Full where UI allows | Limited / read-only on post |
| Outbound draft / lines / delete draft line | Full | Draft where allowed |
| Outbound submit / ship / post | Yes | No (in current UI) |
| Stock transfer | Yes | No |
| WB tokens & sync & link SKU | Yes | No |
| Movements / balances views | Tenant-wide | Seller-scoped |

---

*Document generated for handoff to manual / external review. For technical gates see repository `AGENTS.md` and tests under `backend/tests` and `frontend/tests-e2e`.*

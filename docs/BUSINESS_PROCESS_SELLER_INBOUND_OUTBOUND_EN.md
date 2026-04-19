## Purpose

This document is the **source of truth** for the intended end-to-end business process discussed with the product owner (seller-driven inbound → fulfillment receiving/verification → discrepancy visibility → putaway/stock → outbound picking/packing with scanning).

It is written as **what people do and see** (UX/business rules), not an API spec.

## Actors (roles)

- **Seller (external client)**: creates inbound “applications” (requests), selects planned delivery date, manages lines until the delivery is physically brought. After fulfillment starts receiving, seller becomes read-only and can only observe statuses and discrepancies.
- **Fulfillment (warehouse operator / admin)**: sees seller applications, performs primary acceptance (without recount), then verification recount with actual quantities, marks discrepancies, assigns storage locations (cells), performs putaway and stock posting. Later creates outbound shipments, picks/ships, packs into boxes, can use barcode scanning.

## Core objects (domain entities)

- **Product (SKU/article)**: seller-owned SKU pulled from integration (WB etc.) or created internally. Must have at least: `sku_code` (article), `name`, `photo` (important for receiving), and **barcodes** (for scanning in outbound; can be manual in MVP if integration doesn’t provide).
- **Inbound application (seller delivery plan)**:
  - Header: seller, fulfillment/warehouse, **planned delivery date**, status.
  - Lines: SKU + **planned_qty**.
  - Optional: **boxes plan** (how many boxes seller brings; distribution of SKUs across boxes).
- **Inbound receiving (fulfillment fact)** (can be stored on the same object or a linked object):
  - Per line: **actual_qty** (may be less or more than planned), optional storage location (cell).
  - Box fact (optional): actual boxes + distribution.
- **Discrepancy**:
  - Rule: discrepancy exists if for any line \(actual\_qty \ne planned\_qty\).
  - UX: at minimum, a **red flag/label** in the list and in details; optionally a separate “Discrepancy record”.
  - Visibility: both fulfillment and seller can open and see differences.
- **Stock / balances**: fulfillment-wide on-hand inventory; optionally per storage location.
- **Outbound shipment request**:
  - Header: seller, fulfillment/warehouse, **planned ship date**, status.
  - Lines: SKU + qty to ship (based on available stock).
  - Packing: boxes count + distribution of shipped quantities by box.
  - Picking confirmation: barcode scanning or manual entry.

### Fulfillment UI vocabulary: “Supply and Load”

The fulfillment portal groups **seller supplies** (inbound into the FC) and **load / shipment work** toward the marketplace under the section **Supply and Load** (Russian UI: *Поставки и загрузки*). Two additional document types are planned next to the existing unified list:

- **Download** (working product English term): fulfillment **unloads** goods **to the marketplace** (e.g. FC → marketplace warehouse). A dedicated document will be created, lines filled according to seller needs, and progress tracked by **status**. This is **not** the same object as seller→FC inbound; implementation is pending.
- **Diverge** (working product English term): a **discrepancy act** when plan ≠ fact (or related cases), as a first-class document beyond the inbound `has_discrepancy` flag. Implementation is pending.

## Inbound lifecycle (what people do and see)

### 1) Seller creates an inbound application

- **Seller UI**:
  - Has “My products” (SKU list from integration) and “Applications” (inbound requests).
  - Clicks **Create application**.
  - Adds lines (SKU + planned quantity).
  - Selects **planned delivery date** (when seller will bring goods).
  - Clicks **Save**.
- **Rules**:
  - Application is editable by seller until physical delivery starts (see locking rule).
  - Logging of edits is **not required** for MVP.
- **Expected visible outcome**:
  - Application appears in seller list.
  - Application appears in fulfillment list (read-only plan for fulfillment).

### 2) Seller brings goods → fulfillment primary acceptance (no recount yet)

- **Fulfillment UI**:
  - Sees application in the inbound list with planned date and quantities.
  - Cannot edit seller’s planned quantities.
  - Clicks **Accept product** / **Primary accepted**.
  - Optionally records **number of boxes** received (if seller didn’t specify or changed).
- **Expected visible outcome**:
  - Status becomes **Primary accepted** (accepted but not verified).
  - Seller sees “Accepted (waiting for recount)”.

### 3) Fulfillment verification recount (actual quantities)

- **Fulfillment UI**:
  - Opens application.
  - Sees product **photos** on lines.
  - Enters **actual_qty** per line (can be less or more than planned).
  - Can assign storage location (cell) on each line now, or later during putaway.
  - Confirms verification.
- **Discrepancy rule**:
  - If any line differs: application is marked with a red discrepancy flag/label, visible in lists and details.
  - Seller becomes read-only and can’t change lines anymore.
- **Expected visible outcome**:
  - Status becomes **Verified**.
  - Discrepancy flag is visible when applicable.
  - Seller can open application and see planned vs actual per line.

### 4) Putaway / locations / stock

- **Fulfillment** physically spreads goods into storage locations (cells).
- **UI**: fulfillment assigns/updates storage locations for lines if not set earlier.
- **Expected visible outcome**:
  - Stock/balances reflect received quantities in fulfillment inventory (and per location if tracked).

## Outbound lifecycle (what people do and see)

### 5) Fulfillment creates outbound shipment

- Fulfillment creates a shipment request (not “the same object” as inbound).
- Selects SKUs and quantities based on actual stock and seller context.
- Sets a **planned ship date**.

### 6) Picking / scanning / packing

- Fulfillment picks goods:
  - Confirms picked quantities by **barcode scanning** (preferred) or manual entry (fallback).
- Fulfillment packs into boxes:
  - Creates boxes (e.g., 3 boxes).
  - Distributes picked quantities by box (per SKU per box).
- Expected visible outcome:
  - Shipment reaches “Packed/Ready” and later “Shipped/Handed over”.
  - Seller sees shipment status in their cabinet.

## Locking and permissions (business rules)

- **Seller can edit** inbound application only until fulfillment primary acceptance begins.
- After **Primary accepted / Verified**: seller is **read-only**.
- Fulfillment can modify only fulfillment-owned fields (actual quantities, status transitions, locations, stock posting).

## Gaps vs current implementation (high-signal, factual)

The current repo already implements a WMS-like inbound/outbound, but some key business rules above are not yet in the “business language” UX:

- **Seller vs fulfillment portals**: current app uses one shell with role-based hiding; this conflicts with the “seller at home” mental model unless navigation and labels are separated.
- **Boxes & per-box distribution**: not implemented.
- **Barcode scanning flow**: not implemented as a user flow (even if WB integration stores IDs).
- **Photos on receiving lines**: not implemented in receiving UI.
- **Discrepancy as a first-class visible object**: must be consistently visible to both roles.

## Non-goals (for MVP unless explicitly added)

- Full audit trail of every seller edit.
- Complex lot/serial tracking.
- Printing flows beyond agreed MVP scope in `MVP_DECISIONS_RU.md` (printer 58×40).


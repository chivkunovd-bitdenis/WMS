# WMS-652 C59/R48: real geometry and reachable actions

Source-reviewed basis: analyst brief f3cc69509654702ae2b1e23c92be21a116529e78,
accepted d618 product and corrected C11 cc8e. No product/layout/design changes.
Test source 695a429cd08b4a0b3675cb2d4af0d3f33eeaf9f5 introduced the geometry
contract and three purposeful faults. Final source 1c045a4f2d6c1bb34eeed2f5e79f6e53be2a8a9d
adds only a valid readonly Ozon documents GET boundary. Geometry assertions,
43IDs and mutation helper are byte-identical across that final delta.

## Exact cases and scope

`cases.json` now 43 exact ordered fullName IDs. Original 33 are preserved unchanged;
new 10 use `WMS652.geometry[<variant>;1600x1000-long]`:

- wb-single, wb-group-one, wb-group-many;
- ozon-single, ozon-group-one, ozon-group-many;
- mixed-group-many;
- orders-expired, orders-cancelled;
- selection.

These are **seven valid packing entries**. A single supply has one marketplace;
no nonexistent mixed standalone/group-one case is invented. Canonical order
headers are measured on expired/cancelled order lists; accepted active/delivery/
done supply-summary tables are a different source-backed structure and are not
forced into order columns.

Actual Chrome 1600×1000, real FfFbsOrdersScreen/Workspace/Assembly components,
existing theme/CSS and CDP mouse/key events. Long product/position/seller/route,
formatted dates and supported long size 44/46/48/50/52/54 data are synthetic HTTP
fixtures. Packing measures one common scan bar, nonoverlapping controls/rows,
size/available CIS/sticker/CIS/action column bounds and shared x alignment,
text-box overflow/wrapping and WB-only row QR action. Pointer activates the real
manual CIS/barcode dialog and captures exact order/marketplace request, with
include_order_qr=false for that existing manual action. WB's separate QR button
is also pointer-clicked: exact print-assets request kind/order/supply is asserted.
Ozon has no row order-QR action. No-asset responses deliberately prevent native
printer jobs. Pick→Boxes→Packing tabs are pointer-reachable and the scan input
remains enabled/focusable on return. Existing standalone packed counter and
accepted group readiness summary are preserved separately.

Outside New, exact order header sequence includes Product/Seller/Route/Deadline/
Status. Header and row cell bounds may use normal horizontal scrolling; cells
must not geometrically overlap. Long route remains fully accessible via the
existing tooltip reached by pointer. Long-selection checks nonoverlapping text/
action boxes, actual visible checkbox roots, selected popup, create/preflight
with exact selected IDs and opening add-existing. Existing original 33 provide
actual create/retry/add POST business proof; these 10 add geometry/long-data proof.

Measurements are real getBoundingClientRect/clientWidth/scrollWidth and hit tests;
screenshots are captured per case. This is not JSX-name/CSS-snapshot evidence.
It does not assert mathematical pixel identity, all viewports, all fonts/sizes,
actual app-shell/staging identity, live marketplaces or physical paper. Manual
C61 and broader feature coverage remain separate.

## Purposeful RED and restored GREEN

`geometry-mutants/mutations.json` on source 695:

1. Row print action opacity 0 → seven packing cases **visibility/pointer RED**;
   other 36 PASS. Opacity is chosen to isolate visibility from layout changes.
2. Shift only non-New Seller header left80px → expired/cancelled **geometry RED**;
   other 41 PASS. Saved bounds show the actual intersecting header columns.
3. Hide selected-popup action only for long product data via opacity 0 → long
   selection **visibility/pointer RED**; other 42 PASS. Short original cases still
   execute, so this is not a missing-case/setup failure.

Each product fault is applied only in the isolated checkout, then original bytes
restored in finally and compared. All 43 cases are executed in each negative run;
only the exact target set may fail. Per-case screenshots/measurements retain the
failure state. Final `geometry-final-green/result.json` on exactsource 1c045:
**43 PASS, no skipped/missing, exact ordered cases.json list** after restoration.
Product diff is empty. Chrome --mute-audio remains mandatory.

One final run stopped after 35 case PASS outputs because the disk was full (ENOSPC while saving a JSON artifact), before all cases completed. Only stopped synthetic Chrome profiles were removed; the full final run was then repeated. That interrupted run is not counted as GREEN.

Pre-freeze artifacts are retained as history. First geometry draft had two
incorrect expectations, corrected **by reading accepted source before freeze**:
WB manual CIS/barcode action excludes QR; grouped assembly uses readiness rather
than standalone's literal packed label. These were test-draft errors, not
productRED. Screenshot inspection also exposed an omitted synthetic Ozon docs
GET when visiting Boxes: final fixture supplies requirements_complete=true and
actual exemplar rows with no GTD/RNPT requirement, rather than a 404 error alert.
This is not an external SET/absence assertion or product fix.

## Commands, closure and responsibilities

From frontend start existing isolated Vite:

```sh
npx vite --config tests-e2e/wms652-critical/vite.config.ts
```

Then from root:

```sh
WMS652_EVIDENCE=docs/evidence/WMS-652/critical-fbs-contracts-20261006/geometry-mutants python3 frontend/tests-e2e/wms652-critical/geometry-mutations.py
WMS652_EVIDENCE=docs/evidence/WMS-652/critical-fbs-contracts-20261006/geometry-final-green node frontend/tests-e2e/wms652-critical/browser.mjs
```

Freeze closure: all 12 files under frontend/tests-e2e/wms652-critical, existing
frontend package manifests/lock and actual product import graph. New files are
geometry.mjs and geometry-mutations.py. Whole-product contract separately uses
scripts/ci/tests/test_product_scope.py (51 cases) and root-owned product_scope.py;
test-before source 9bb8b93254a7f79da7d8fd73eedfa75a1cf69b41 remains unchanged.
Registry/CI/trusted activation and acceptance remain root/independent-role owned.

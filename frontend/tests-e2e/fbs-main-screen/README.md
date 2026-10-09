# Main FBS screen browser gate

This suite loads the compiled application at `/app/ff/fbs`, talks to the real
FastAPI server, and reads/writes a disposable PostgreSQL database. Celery and
Redis execute the WB synchronization jobs. Only the marketplace is emulated.
There is no WMS API interception, component harness, `skip`, or `xfail`.

Run with Docker, Node 24 and an installed `@playwright/test`:

```sh
WMS_PLAYWRIGHT_MODULE=/absolute/path/to/@playwright/test/index.mjs \
  bash scripts/ci/run_fbs_main_screen.sh
```

The scoped GitHub workflow runs on pushes to `codex/fbs-main-screen-ci`. It
uploads the tested SHA, browser screenshots, per-case results and request URLs,
build/server logs, and an independent database check of physical stock. Each
case gets a fresh browser context. `results.json` distinguishes setup failures
from failures during the scenario; a failed initial list is not evidence of
many separate product defects. Unexpected React exceptions fail a case.

The runner creates a unique compose project. Its cleanup removes only that
project. Host ports are fixed, so parallel runs on one host intentionally fail
to bind instead of using somebody else's service. The seed requires the explicit
disposable flag, container database host `db`, database `wms`, and loopback API.
The browser rejects non-loopback origins. WB and Ozon upstream base URLs point
to test emulators, never the live marketplaces. Existing application code,
global CI, and permanent guards are unchanged.

## Executable coverage

All cases below are in `browser.mjs`. A case is executable; it is called passed
only after its browser/API run succeeds on the recorded SHA.

| Scenario | Case | Actual boundary and expectation |
| --- | --- | --- |
| S1 | `S1-six-tabs-and-exact-membership` | Browser table IDs against explicitly inserted database records; six tabs; orders versus supplies; WB past/future deadline and Ozon past deadline membership. Does not endorse a deadline prohibition. |
| S1 / S12 | `S1-S12-arriving-order-refresh-and-no-sync-duplicate` | Open browser, create a new external WB order, run actual WMS/Celery synchronization, refresh the existing screen, repeat sync, assert one record/one row. The test API sync represents a background event, not an admin button scope decision. |
| S2 | `S2-marketplace-seller-search-empty` | Real worklist requests and exact visible IDs after marketplace/seller/search changes; an independently absent identifier produces an empty result. |
| S2 | `S2-two-wb-warehouses-exact-membership` | Real WB seller B order on warehouse 501002 and WB orders on 501001; exact distinct sets; changing to Ozon resets warehouse. Ozon has its own external warehouse identifier. |
| S3 | `S3-ozon-position-fields` | Real serializer and browser show every Ozon position's own name/article and one size per position in the size column that replaces SKU (WMS-719); SKU is not rendered and existing table columns stay. |
| S4 | `S4-hidden-selection-and-loaded-select-all` | Selection survives search; select-all adds only the loaded result; mixed marketplaces cannot form a supply; selected dialog includes hidden order; marketplace change clears selection. |
| S4 | `S4-not-published-selectable` | `not_published` is not a UI selection/create blocker. |
| S4 | `S4-selected-dialog-remove-and-clear` | Remove one order from the selected dialog, retain the other, clear all and verify checkboxes and panel. |
| S2 / S4 | `S2-S4-selection-resets-and-warehouse-reset` | Actual seller/warehouse/tab changes clear selection; leaving and returning to New resets warehouse to All. |
| S4 | `S4-last-row-remains-clickable-under-selection-panel` | Browser geometry at 1280×800 plus actual click of the last unchecked row under a visible selection panel. |
| S4 / roles | `S4-operator-role` | Actual operator login can select; admin synchronization action is absent. |
| S5 | `S5-real-preflight-single-wb` | Actual server preflight, WB delivery choices, enabled creation after compatible preflight, cancellation keeps selection. |
| S5 / S6 | `S5-S6-real-create-and-add-existing-wb` | Browser creates a real WB supply in the emulator through WMS, adds a second order through WMS, verifies success navigation, selection clearing, removal from New, and a fresh committed workspace API read containing both IDs once. Runs after read-only cases because it mutates the fixture. |
| S5 / S7 | `S5-S7-two-sellers-two-wb-warehouses-common-assembly` | Browser forms two upstream WB supplies and one shared assembly task; verifies seller/warehouse/order composition and fresh task API read; restores `supply_ids` after reload; nested supplies appear once. |
| S6 | `S6-no-compatible-ozon-supply` | Actual active-supplies API produces no matching Ozon supply; UI explains this and cannot submit a nonexistent target; closing retains selection. |
| S7 | `S7-supply-columns-document-url-reload` | Eight supply columns, document URL, reload restores document, close clears URL. Database supplies have no upstream WB counterpart, so this is not proof of upstream delivery. |
| S8 | `S8-missing-upstream-qr-does-not-open-document` | Actual tracking/cargo-place API calls for a deliberately nonexistent upstream supply; no ready preview; visible error; print click does not navigate the row. |
| S8 | `S8-ready-wb-cargo-qr-preview-and-copies` | Actual WMS API creates a cargo place in the WB emulator; the main table downloads the real QR asset and opens a ready preview; copy field accepts 99; closing clears preview; no document navigation. This tests cargo-place QR, not shipped-supply QR or physical paper. |
| S9 | `S9-ozon-cancel-confirmation-only` | Selected posting is in confirmation dialog; cancel is enabled; dismiss retains selection. It does not execute marketplace cancellation. |
| S10 | `S10-cancelled-wb-entry-marketplace` | Real list-to-open dialog, empty response, disabled next page, close; entry hidden for Ozon. |
| S11 | `S11-export-hidden-selected-wb` | Actual browser download contains the selected hidden order and excludes the unselected visible posting. |
| S11 | `S11-export-ozon-positions-known-defect` | Actual downloaded file must contain exactly both Ozon positions, their own articles, and quantities 2 and 3 in the Quantity column, total 5. This is intentionally a normal failing assertion on the current defect, with no expected-failure escape. |
| S12 | `S12-independent-metric-seller-and-refresh` | Actual statistics API for seller A while table filters seller B; explicit durations 6/18/30 hours yield 18.0 hours, 3 orders, 33%/67%; a negative duration control contributes nothing. Table refresh preserves its own filter. |
| S12 | `S12-valid-custom-dates-and-month` | Month and complete valid custom range query the actual API; checks Moscow day bounds and independently known count/average. Empty custom dates are not approved by this case. |
| Owner stock contract | `fbs_main_screen_verify.py` | Independent SQL read after browser operations compares physical inventory totals per product to the seed snapshot. Reserving, creating, adding must not reduce stock. This does not cover shipment deduction. |

## Remaining gaps and blockers

These are gaps, not passed checks. No complete-screen coverage or production
browser acceptance is claimed.

* S1: grouping assembly tasks, hidden/unmapped external active orders, and every
  role/tab combination are not covered. The meaning of the WB deadline remains
  a business question; this suite does not turn lack of checkboxes into a rule.
* S2: delayed response races, debounce timing, group
  search and lists exceeding 500 need additional fixtures/scenarios. The 500
  implementation cap is deliberately not established as a business rule.
* S3: actual marketplace barcodes, image hover/focus/broken image, long names,
  marking errors and non-openable external documents still need coverage.
* S4: disappearance during refresh remains untested; geometry has one desktop
  viewport, not all supported screen sizes.
* S5: partial creation,
  unknown result and retry with one idempotency key remain untested. The current
  seed synchronizes live-emulated WB orders for sellers A/B; seller C's imported
  history sentinel stays outside those syncs. Synthetic screen records are not
  used for successful upstream creation.
* S6: compatibility rejection combinations, recoverable API errors and
  concurrent/idempotent adds remain untested.
* S7: picked counters and navigation under unpacked state remain untested.
* S8: shipped-supply WB QR, ready Ozon box labels, partial assets, full copy/size controls,
  applied confirmations and popup behavior remain untested. The existing Ozon
  test emulator is not connected here; directing Ozon to the WB emulator gives
  an honest unsupported response rather than a simulated successful label.
  CI cannot establish physical paper output.
* S9: actual cancellation and partial failure require an external Ozon emulator
  supporting `/v2/posting/fbs/cancel`. The existing WMS445 Ozon emulator does not
  implement cancellation. No live Ozon request is permitted.
* S10: nonempty rows, inherited seller, local search, refresh, page 2 and opening
  a supply still need a cancelled-after-pack fixture.
* S11: escaping, WB column fidelity and export with large/multiple selections
  remain untested. The explicit Ozon position/quantity defect keeps this gate
  red until the product is separately fixed.
* S12: exact cohort boundaries, nonempty seller B,
  stale responses, visible-only polling and errors remain
  untested. Scope of admin synchronization and the desired statistical cohort
  are not silently invented by this suite. Empty custom dates are not endorsed.
* S13: a controlled actual React render exception and reset after switching a
  document are not covered. A network/HTTP failure cannot substitute for this.
  A temporary test-bundle mutation can exercise it without WMS API mocks.

## Minimal mutation proof

The runner first executes S1 alone on the original bundle. Only after that
baseline passes does it temporarily replace the single `setOrders(page.items)`
with `setOrders([])`, rebuild and rerun S1 on the same unchanged database.
`mutation/proof.json` must establish nonempty known expected IDs, an actual
worklist HTTP 200 with nonempty items, empty DOM rows, and no React error.
Login, build or network failures cannot satisfy the proof. Source restoration
is in the cleanup trap and the normal bundle is rebuilt before the full suite
executes arrival/create/add. Mutation evidence is separate from normal results.
This mode is implemented but not yet live-verified on the current SHA.

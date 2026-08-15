# Wave 2. FBS - v rabote i postavki

Ekран: FBS - "Novye" / "V rabote" / kartochka postavki
Zadachi: FBS-05, FBS-06, FBS-18, FBS-20
Stadiya: backend gate + TypeScript gate + live browser product gate
Status: DEV_BROWSER_APPROVED_FOR_MERGE
Commit: 5a51efc
Raунd: 1

## Testy

- Backend: `PYTHONDONTWRITEBYTECODE=1 WMS_TEST_DATABASE_URL=sqlite+aiosqlite:////tmp/wms-fbs-work-...sqlite pytest backend/tests/test_fbs_supply_from_orders.py -q -p no:cacheprovider`
- Result: `16 passed, 1 skipped in 55.13s`
- TypeScript: `./frontend/node_modules/.bin/tsc -b frontend/tsconfig.json --pretty false`
- Result: success, 0 errors
- Ruff: `ruff check app/api/fbs_supplies.py app/services/fbs_supply_service.py app/services/fbs_workspace_service.py tests/test_fbs_supply_from_orders.py`
- Result: `All checks passed!`

## Browser

Browser: visible external Google Chrome 151.0.7922.138, controlled through Chrome DevTools Protocol on `127.0.0.1:9227`.
This was not Playwright, not headless, and not screenshots-only.

Local stand:
- Frontend: `http://127.0.0.1:18431/app/ff/fbs`
- Backend: `http://127.0.0.1:18430`, `WMS_AUTO_CREATE_SCHEMA=1`
- Disk note: persistent sqlite could not be opened because the system disk was at 99-100 percent. For the visual browser gate I used in-browser HTTP fixtures for FBS worklist/supply responses, while the real backend behavior was checked by the backend test suite above.

## Proklikano v zhivom Chrome

- FBS-18: opened tab "V rabote"; table `fbs-18-supplies-table` was visible and grouped by one supply row, not by orders.
- FBS-18: verified visible columns: supply name/number, seller, warehouse, orders/units, boxes, status, shipment date.
- FBS-06: verified external WB-processing order explanation: order is not shown as "New"; active tab shows a human explanation that a WB supply exists without a local WMS card.
- FBS-18: clicked supply row `FBS-LIVE-WORK`; supply workspace opened.
- FBS-20: verified stages "Podbor" and "Upakovka i markirovka".
- FBS-20: verified automatic picking pass explanation: "Podbor propuschen avtomaticheski..." for no-address/no-distribution case.
- FBS-20: verified started supply does not show primary "Nachat rabotu s postavkoy" button.
- FBS-05: on "Novye", selected two compatible orders and opened "Dobavit v sushchestvuyushchuyu postavku".
- FBS-05: in the dialog, selected compatible supply `FBS-LIVE-WORK - Seller Odin - WB Podolsk - V rabote`.
- FBS-05: submitted add-to-existing; workspace opened and displayed partial WB read-back: one order accepted, one rejected with "WB read-back ne podtverdil zakaz".
- FBS-05: from the supply workspace, opened "Dobavit zakazy", saw compatible orders table, selected an order, submitted it, and saw the supply update.

## 6a audit

- "Dobavit v sushchestvuyushchuyu postavku" on New tab: FBS-05.
- Compatible existing supply select: FBS-05.
- Partial read-back with accepted/rejected orders: FBS-05.
- "Dobavit zakazy" inside supply workspace: FBS-05.
- External WB supply explanation without a local card: FBS-06.
- Active tab grouped by supplies: FBS-18.
- Active table columns supply/seller/warehouse/orders/units/boxes/status/shipment date: FBS-18.
- Click supply row to open card: FBS-18.
- Stages "Podbor" and "Upakovka i markirovka": FBS-20.
- Disabled/auto-passed picking reason: FBS-20.
- No primary start button on already started supply: FBS-20.

No visible element found in this gate that could not be mapped to FBS-05, FBS-06, FBS-18, or FBS-20.

## Nahodki

- Stop: 0
- Tormoz: 1 - persistent sqlite live seed was blocked by system disk pressure (`unable to open database file`); visual browser gate used fixture FBS data in visible Chrome, while backend behavior was covered by real pytest.
- Hvost: 0

## Blockery

No merge blocker for this screen after the checks above.
Screenshots were not written because free disk space was around 117-150 MiB and the user explicitly forbade deleting files without permission.


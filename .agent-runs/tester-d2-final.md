# WMS-654 additional warehouse-map suggestion contract

This tester change adds two focused Vitest DOM contracts for the real `FfWarehouseMapPage`; it does not alter product code or existing tests.

## Command and current RED

From `frontend/`:

```sh
npm run test:unit -- src/screens/ff/warehouse-map/FfWarehouseMapPage.wms654-suggestion.test.tsx --maxWorkers=1
```

On `a469cebec` the command exits 1 with both new tests red. C2 reports that the actual page never requests the authoritative suggestion. C7 sees zero suggestion requests after rows А then Б are selected. The full error record is in `.agent-runs/tester-d2-red.log`.

## Expected behavior after the product fix

With existing map data containing ambiguous text code `А 1.9` for a saved `(side=1, tier=null, position=9)` cell, choosing row `А`, disabled sides, and tier `1` must call `GET /api/warehouses/wh-current/locations/suggest` with `rack_name=А`, `use_sides=false`, `use_tiers=true`, and `tier=1` (without `side`). The returned `{ position: 1, code: "А 1.1" }` must become the visible position and preview.

When the operator changes row А to Б and enters manual position 42, a late result for А, and even the current automatic result, must not overwrite the visible current-row manual value or preview `Б 1.1.42`.

The contract intentionally uses only mocked `fetch`, jsdom, and visible form state. It does not prescribe a callback name or product test export.

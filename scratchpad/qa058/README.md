# WMS-058 — local browser QA handoff

Prepared from common commit `5c371f39ccd836be96f85d4ffb68b8e52d5864cf`; its backend/app and frontend match production-code commit `0a672b406b932eca76378cf247952338f88d702c`. This branch changes only synthetic QA files. No browser acceptance is claimed: CUA returned `browsers: []`; Chrome was not used.

The backend imports this isolated checkout. The frontend runs from the common checkout. Backend/UI ports: **18558 / 15558**. Local PostgreSQL DB: `wms058_browser_5c371f39` on `127.0.0.1:5432`, user `deniscivkunov`. There are zero marketplace accounts, stock sync is disabled on the synthetic binding, and runtime denies non-loopback socket connections. No real WB/Ozon calls or credentials are used.

Sign in at http://127.0.0.1:15558 with **qa058@example.com / password123** (synthetic only). Select **QA058 Warehouse** and **QA058 Seller** when the screen offers filters.

## Operator scenarios

1. Open `/app/ff/products`. Compare these values with the product selector: open `/app/ff/mp-shipments`, open document **QA058-draft**, then **Добавить товары**. The selector uses the real available-products API. Before any picking:

| SKU | Physical | FBS order reserves | Other stock direction | Active units allocation | Catalog free FBO / product selector |
| --- | ---: | ---: | ---: | ---: | ---: |
| QA058-P | 10 | 3 | 2 | 0 (saved pool2 is inactive in percentage mode) | **5 / 5** |
| QA058-U | 10 | 3 | 2 | 2 | **3 / 3** |
| QA058-Z | 1 | 1 | 0 | 0 | **0 / 0** |

2. Open `/app/ff/unload-pick/ebcac55a-305c-580f-a9b5-abf8b1fb4c84` (document **QA058-sources**). For both P and U, source **QA058-A** holds4 with one foreign FBS pick, so available3; **QA058-B → Короб WHB-QA058-BOX** holds4 with one foreign FBS pick, so available3; sorting is labeled **Без ячеек**, holds2 with no assigned pick, available2. Z holds1 in sorting but FBO available0. These are alternative source capacities; do not add them to claim a larger warehouse ceiling. Optional mutation after recording the initial display: collect U3 from the box. Its warehouse FBO ceiling becomes0, and reread must show no more U available from any source. This existing MP picking operation physically transfers stock into pick allocation; it is not a packaging action.

3. Open `/app/ff/fbs?supply_id=81cecf97-1a47-57f9-8ffc-8423817bcb92` (**QA058 own**) and open picking. P/U source capacities are3/3/2. Z is **available1 for its own FBS order**, although catalog/FBO selector show0. Pick Z1, reread, then undo. The FBS pick/undo must preserve its physical quantity1 and reservation1; only pick facts change. The foreign supply `a018c20b-b204-5e6e-bf8e-6ebfe50aba32` already has two picks per P/U: one from A, one from the box. Those were created through the real WB picking service; no physical movement occurred.

4. Optional separate legacy observation: `/app/ff/fbs?supply_id=44c8e119-cbd2-5374-bf9a-5695a742cb37`, **QA058 legacy**, Ozon. Product QA058-L physically2 in sorting box WHB-QA058-LEGACY, reserve1, one historic picked fact with movement/source-container NULL. API reports source label **Место подбора (тара не сохранена)**, picked1, no container path, and a separate real box with physical2/available1/picked0. The previously reported UI fallback **Россыпь/Россыпью** must be recorded separately; this seed does not invent which box the old pick came from. No redesign or source flags were added.

Packing is only a recorded fact. It must not alter stock/reservations or block navigation. No handover or marketplace operation is needed for these availability scenarios.

## Baseline already read through the real HTTP proxy

All nine reads returned200: catalog summary, MP available-products, MP sources, and own/foreign/legacy FBS pick-options plus workspaces (the exact endpoint map is in snapshot.py). Catalog/P/U/Z and source capacities match the table above. `before.json` holds complete replies and SQL rows; `baseline.log` is a compact rendering.

SQL baseline: 8 inventory balance rows totaling23 units; 8 initial receipt movements totaling+23; 7 WB reserve rows totaling7 plus one Ozon position reserve1; 4 WB active picks plus one historic Ozon NULL pick; 2 saved allocation pools; 2 stock directions; 0 MP reservations/allocations; 0 packaging tasks/lines; 0 marketplace accounts. `blocked-network.jsonl` was absent (no external connection attempts).

Targeted tests on this common code: `test_fbs_catalog_free_fbo.py` plus `test_two_wb_supplies_cannot_assign_same_physical_unit` = **6 passed** with `pytest -n auto`, 8.75s. No full suite was run. HTTP/SQL evidence is preparation for root's actual clicks, not a substitute for browser acceptance.

## Start/restart and read after operator actions

Run each server in its own persistent terminal. Do not restart another agent's ports.

```sh
cd /Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-wms058-browser
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python -m uvicorn runtime:app --app-dir scratchpad/qa058 --host 127.0.0.1 --port 18558
```

```sh
cd /Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-stage/frontend
VITE_API_PROXY=http://127.0.0.1:18558 VITE_DEV_CLIENT_PORT=15558 ./node_modules/.bin/vite --host 127.0.0.1 --port 15558 --strictPort
```

Read-only reread, after clicking:

```sh
cd /Users/deniscivkunov/Projects/WMS/.worktrees/backlog40-wms058-browser
/Users/deniscivkunov/Projects/WMS/backend/.venv/bin/python scratchpad/qa058/snapshot.py after.json
```

`seed.py` creates the schema and records only in the named empty local DB. It refuses a nonempty schema and does not reset a running browser scenario. `seed.json` contains deterministic product/supply/request IDs and the locally generated sorting-location ID. The initial setup had a `.test` email rejected by the real login validator; only the synthetic email was corrected to `.com` before baseline capture. The login and all workspaces now return200.

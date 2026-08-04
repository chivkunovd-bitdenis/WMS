# WB Marketplace API Emulator

Standalone HTTP service that mimics Wildberries Marketplace API v3 (`/api/v3/...`) for WMS FBS integration testing.

WMS switches to the emulator via a single environment variable: `WILDBERRIES_MARKETPLACE_API_BASE`.

## EMU-010 scaffold

- FastAPI + SQLite (persistent file on volume)
- Raw `Authorization: <token>` header (no `Bearer` prefix)
- Unknown token on `/api/v3/*` → `401 Unauthorized`
- `GET /health` → `200` (no auth)
- Empty router mounts for orders, supplies, media/meta, warehouses, admin (implemented in EMU-020+)

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `WB_EMULATOR_DB_PATH` | SQLite database file path | `/data/wb_emulator.sqlite` |
| `WB_EMULATOR_TOKEN_MAP` | JSON object `{"<token>": "<seller_key>", ...}` | `{}` |
| `WB_EMULATOR_TOKEN_MAP_FILE` | Path to JSON file with the same shape (overrides env keys) | — |

Example:

```bash
export WB_EMULATOR_DB_PATH=/tmp/wb_emulator.sqlite
export WB_EMULATOR_TOKEN_MAP='{"test-token-vitalik":"vitalik","test-token-other":"other"}'
```

## Run locally

From repository root:

```bash
python -m venv .venv-emulator
source .venv-emulator/bin/activate
pip install -r wb_emulator/requirements.txt
export PYTHONPATH=.
export WB_EMULATOR_DB_PATH=/tmp/wb_emulator.sqlite
export WB_EMULATOR_TOKEN_MAP='{"dev-token":"seller_a"}'
uvicorn wb_emulator.main:app --reload --port 8099
```

Health check:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8099/health
# 200

curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8099/api/v3/orders/new
# 401

curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: dev-token" http://127.0.0.1:8099/api/v3/orders/new
# 200 (auth ok, orders list)
```

## Docker

### Full WMS stack with emulator

From repository root (overlay on `docker-compose.yml`):

```bash
cp wb_emulator/.env.example wb_emulator/.env   # optional; edit token map
docker compose -f docker-compose.yml -f docker-compose.emulator.yml up -d --build
```

`api`, `celery_worker`, and `celery_beat` receive `WILDBERRIES_MARKETPLACE_API_BASE=http://wb-emulator:8000`.
Optional seed JSON: place files under `wb_emulator/seed/` (mounted read-only at `/seed`).

### Emulator image only

Build from repository root:

```bash
docker build -f wb_emulator/Dockerfile -t wb-emulator:local .
docker run --rm -p 8099:8000 \
  -v wb-emulator-data:/data \
  -e WB_EMULATOR_TOKEN_MAP='{"dev-token":"seller_a"}' \
  wb-emulator:local
```

## Tests

```bash
export PYTHONPATH=.
pytest wb_emulator/tests -q
```

### Operator seed (FBSFLOW-120 / TC-23)

Three sellers (`token-a`/`token-b`/`token-c` → `seller_a`/`seller_b`/`seller_c`), 15 scenario orders in `seed/order_templates.json` (requiredMeta, PVZ, B2B, cargo types, cancelled, near-deadline).

```bash
export PYTHONPATH=.
export WB_EMULATOR_TOKEN_MAP='{"token-a":"seller_a","token-b":"seller_b","token-c":"seller_c"}'
python -m wb_emulator.seed.load_seed --db-path /tmp/wb_emulator.sqlite
# or POST /__admin/seed with X-Admin-Token
pytest wb_emulator/tests/test_emulator_operator_seed.py -q
```

### WMS ↔ emulator FBS stock cycle (STOCK-100)

End-to-end proof that WMS stock sync and order intake talk to this service over HTTP
(`PUT/POST /api/v3/stocks/{warehouseId}`, `GET /api/v3/orders/new`, admin purchase).

From repository root:

```bash
cd backend && pytest tests/test_fbs_stock_emulator_integration.py -q
```

Cycle covered: WMS publish amount 1 → emulator readback 1 → admin purchase (1 created, 1 rejected) →
emulator amount 0 → WMS order intake + reserve 1 → next sync confirmed 0. FBO reserve on another
WMS warehouse does not change FBS publish. Uses in-process `httpx.ASGITransport` (real HTTP stack,
no MockTransport on both sides). Prod compose guard: `docker-compose.prod.yml` has no `wb-emulator`.

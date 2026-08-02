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
# 404 (auth ok, route not implemented yet)
```

## Docker

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

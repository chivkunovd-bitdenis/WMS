# OpenAPI — FBS operator flow

## Экспорт (канонический артефакт)

```bash
cd backend && .venv/bin/python scripts/export_fbs_openapi.py
```

Пишет **`openapi/fbs-operations.openapi.json`** (подмножество путей `/operations/fbs-*`).

Проверка контракта: `pytest tests/test_fbs_openapi_contract.py`.

## Runtime (Swagger)

| Среда | URL |
|-------|-----|
| Локально | `http://localhost:8000/docs` |
| JSON | `GET /api/openapi.json` |

Wire-contract для фронта — **`BACKEND_CONTRACT.md`** и **`ERROR_CATALOG_RU.md`**; OpenAPI дополняет, но не заменяет семантику `retryable` и idempotency.

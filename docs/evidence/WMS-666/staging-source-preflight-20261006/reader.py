"""Exact Railway staging supply, SELECT only, no credentials in output."""
import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

PROJECT = "c28e681d-4535-4c96-ac97-c7b600a7f8e4"
ENVIRONMENT = "58a08b66-1290-45a2-8737-e3d7408389e5"
SERVICE = "e4a67f11-4318-4386-b9f9-fe5ae0d4f5cc"
SUPPLY = "9b3993c3-dffd-5f14-b7b0-2ccf0f495b57"

async def read(proof):
    from sqlalchemy import text
    from app.db.session import SessionLocal
    expected = {"RAILWAY_PROJECT_ID": PROJECT, "RAILWAY_ENVIRONMENT_ID": ENVIRONMENT,
                "RAILWAY_SERVICE_ID": SERVICE}
    if any(os.environ.get(k) != v for k, v in expected.items()):
        proof["failure_code"] = "exact_staging_runtime_identity_mismatch"
        return
    proof["runtime_identity_verified"] = True
    async with SessionLocal() as session:
        if session.bind.dialect.name != "postgresql" or session.bind.url.host != "postgres.railway.internal":
            proof["failure_code"] = "expected_private_staging_postgresql_unavailable"
            return
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        rows = (await session.execute(text("""
            SELECT id, tenant_id, seller_id, warehouse_id, marketplace, name, status, source,
                   current_setting('transaction_read_only') AS read_only
            FROM fbs_supplies WHERE id=:supply
        """), {"supply": uuid.UUID(SUPPLY)})).mappings().all()
        proof["found"] = len(rows) == 1
        proof["supply_rows"] = len(rows)
        if rows:
            proof["supply"] = {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in rows[0].items()}
            if len(rows) != 1 or rows[0]["read_only"] != "on":
                raise RuntimeError("unexpected_scope")
            orders = (await session.execute(text("""
                SELECT o.id AS order_id, o.marketplace, o.status, o.external_order_id,
                       o.wb_order_id, p.id AS position_id, p.ozon_sku, p.quantity
                FROM fbs_orders o LEFT JOIN fbs_order_products p ON p.order_id=o.id
                WHERE o.supply_id=:supply AND o.tenant_id=:tenant
                ORDER BY o.id, p.id
            """), {"supply": uuid.UUID(SUPPLY), "tenant": rows[0]["tenant_id"]})).mappings().all()
            proof["composition"] = [{k: str(v) if isinstance(v, uuid.UUID) else v for k, v in row.items()} for row in orders]
        await session.rollback()
        proof["execution_status"] = "READ_ONLY_PREFLIGHT_FINISHED"

proof = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "target_supply_id": SUPPLY,
         "project_id": PROJECT, "environment_id": ENVIRONMENT, "service_id": SERVICE,
         "execution_status": "NO_SQL_RESULT", "mutation_calls": [], "commit_called": False}
try:
    asyncio.run(read(proof))
except Exception as exc:
    proof["error_type"] = type(exc).__name__
proof["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
print("WMS666_STAGING_READ_PROOF=" + json.dumps(proof, ensure_ascii=False))

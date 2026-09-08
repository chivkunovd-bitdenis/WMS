"""Read-only HTTP and SQL evidence for the isolated QA058 browser scenario."""

import asyncio
import json
import sys
from runtime import QA, DB_NAME
from app.db.session import engine
from httpx import AsyncClient
from sqlalchemy import text

TABLES = (
    "inventory_balances",
    "inventory_movements",
    "fbs_order_reservations",
    "fbs_order_product_reservations",
    "fbs_order_picks",
    "fbs_order_product_picks",
    "fbs_binding_stock_pools",
    "stock_directions",
    "marketplace_unload_reservations",
    "marketplace_unload_pick_allocations",
    "packaging_tasks",
    "packaging_task_lines",
    "marketplace_accounts",
)


async def main():
    info = json.loads((QA / "seed.json").read_text())
    out = {"http": {}, "sql": {}}
    async with AsyncClient(base_url="http://127.0.0.1:15558/api", timeout=30) as c:
        login = await c.post(
            "/auth/login", json={"email": info["email"], "password": info["password"]}
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        endpoints = {
            "catalog": "/operations/inventory-balances/summary?warehouse_id="
            + info["warehouse"],
            "picker": "/operations/marketplace-unload-requests/available-products?warehouse_id="
            + info["warehouse"]
            + "&seller_id="
            + info["seller"],
            "mp_sources": "/operations/marketplace-unload-requests/"
            + info["mp"]["sources"]
            + "/pick-options",
        }
        for key, supply in info["supplies"].items():
            endpoints["fbs_" + key] = (
                "/operations/fbs-supplies/" + supply + "/pick-options"
            )
            endpoints["workspace_" + key] = (
                "/operations/fbs-supplies/" + supply + "/workspace"
            )
        for key, url in endpoints.items():
            r = await c.get(url, headers=headers)
            out["http"][key] = {"status": r.status_code, "data": r.json()}
            assert r.status_code == 200, (key, r.status_code, r.text)
    async with engine.connect() as conn:
        assert await conn.scalar(text("select current_database()")) == DB_NAME
        for table in TABLES:
            out["sql"][table] = list(
                (
                    await conn.execute(
                        text(f"SELECT row_to_json(t) FROM {table} t ORDER BY id")
                    )
                ).scalars()
            )
    out["blocked_network"] = (
        (QA / "blocked-network.jsonl").read_text()
        if (QA / "blocked-network.jsonl").exists()
        else ""
    )
    target = QA / (sys.argv[1] if len(sys.argv) > 1 else "before.json")
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    for row in out["http"]["catalog"]["data"]:
        print(
            "catalog",
            row.get("sku_code"),
            {
                k: row[k]
                for k in [
                    "quantity",
                    "reserved",
                    "quantity_fbs",
                    "quantity_free_fbo",
                    "available",
                ]
            },
        )
    for key in ["picker", "mp_sources", "fbs_own", "fbs_foreign", "fbs_legacy"]:
        print(key, json.dumps(out["http"][key]["data"], ensure_ascii=False))
    print("SQL row counts", {k: len(v) for k, v in out["sql"].items()})
    print("blocked network", repr(out["blocked_network"]))
    await engine.dispose()


asyncio.run(main())

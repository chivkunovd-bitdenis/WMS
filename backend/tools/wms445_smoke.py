"""Run one real WMS Ozon flow against the local HTTP emulator, then replay deliver."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, cast

from httpx import AsyncClient

from tools.wms445_local_http import install_http_guard
from tools.wms445_seed import ADMIN_EMAIL, PASSWORD, local_url


async def smoke(api_base: str, manifest: dict[str, Any]) -> dict[str, Any]:
    install_http_guard()
    steps: list[dict[str, Any]] = []
    async with AsyncClient(base_url=local_url(api_base), timeout=90) as client:
        auth = await client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
        auth.raise_for_status()
        headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}

        async def req(method: str, path: str, body: Any = None) -> dict[str, Any]:
            response = await client.request(method, path, headers=headers, json=body)
            steps.append({"path": path, "status": response.status_code})
            if response.status_code >= 400:
                raise RuntimeError(
                    f"{path}: HTTP {response.status_code}: {response.json().get('detail')}"
                )
            return cast(dict[str, Any], response.json())

        order_id = next(row["id"] for row in manifest["orders"] if row["external_id"] == "445-a-0")
        workspace = await req(
            "POST",
            "/operations/fbs-supplies/from-orders",
            {
                "name": "WMS445 Ozon HTTP smoke",
                "order_ids": [order_id],
                "planned_delivery_type": "warehouse_sc",
                "idempotency_key": "wms445-http-smoke-create",
            },
        )
        supply_id = workspace["supply"]["id"]
        base = f"/operations/fbs-supplies/{supply_id}"
        if workspace["supply"]["status"] != "in_delivery" and not any(
            box["ozon_assembled"] for box in workspace["boxes"]
        ):
            workspace = await req("POST", base + "/start-work")
            positions = workspace["orders"][0]["positions"]
            for pos in positions:
                for index in range(pos["quantity"]):
                    workspace = await req(
                        "POST",
                        base + "/pick/manual",
                        {
                            "location_id": manifest["source_ids"][index % 2],
                            "product_id": pos["product_id"],
                            "order_id": order_id,
                            "idempotency_key": f"wms445-smoke-pick:{pos['id']}:{index}",
                        },
                    )
            task_id = workspace["supply"]["packaging_task_id"]
            task = await req("GET", f"/operations/packaging-tasks/{task_id}")
            lines = {line["product_id"]: line["id"] for line in task["lines"]}
            for pos in positions:
                for index in range(pos["quantity"]):
                    await req(
                        "POST",
                        f"/operations/packaging-tasks/{task_id}/lines/{lines[pos['product_id']]}/pack",
                        {
                            "quantity": 1,
                            "order_id": order_id,
                            "idempotency_key": f"wms445-smoke-pack:{pos['id']}:{index}",
                        },
                    )
            workspace = await req(
                "POST", base + "/boxes", {"count": 1, "idempotency_key": "wms445-smoke-box"}
            )
            box_id = workspace["boxes"][0]["id"]
            workspace = await req(
                "POST",
                f"{base}/boxes/{box_id}/orders",
                {"order_product_ids": [p["id"] for p in positions]},
            )
            workspace = await req("POST", f"{base}/boxes/{box_id}/retry-qr")
        delivered = await req(
            "POST", base + "/deliver", {"idempotency_key": "wms445-smoke-deliver"}
        )
        replay = await req("POST", base + "/deliver", {"idempotency_key": "wms445-smoke-deliver"})
        reread = await req("GET", base + "/workspace")
        assert (
            delivered["supply"]["status"]
            == replay["supply"]["status"]
            == reread["supply"]["status"]
            == "in_delivery"
        )
        return {
            "supply_id": supply_id,
            "status": "in_delivery",
            "steps": steps,
            "progress": reread["progress"],
            "route": reread["supply"]["delivery_route"],
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:18084")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    report = asyncio.run(smoke(args.api_base, json.loads(Path(args.manifest).read_text())))
    Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps({"supply_id": report["supply_id"], "status": report["status"]}))

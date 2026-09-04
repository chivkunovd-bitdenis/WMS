"""Create reproducible WMS + WB-emulator data for the real browser FBS gate."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import httpx

from tests.fbs_operator_emulator_seed import seed_operator_emulator_wms

API_BASE = os.environ.get("FBS_E2E_API_BASE", "http://127.0.0.1:8000")
EMULATOR_BASE = os.environ.get("FBS_E2E_EMULATOR_BASE", "http://wb-emulator:8000")
EMULATOR_ADMIN_TOKEN = os.environ.get("WB_EMULATOR_ADMIN_TOKEN", "fbs-e2e-admin")
WB_WAREHOUSE_ID = 501001


async def _require(response: httpx.Response, *, expected: tuple[int, ...] = (200,)) -> Any:
    if response.status_code not in expected:
        raise RuntimeError(
            f"{response.request.method} {response.request.url}: "
            f"{response.status_code} {response.text}"
        )
    return response.json()


async def _wait_job(
    client: httpx.AsyncClient, headers: dict[str, str], job_id: str
) -> dict[str, Any]:
    last_body: dict[str, Any] | None = None
    for _ in range(240):
        body = await _require(
            await client.get(f"/operations/background-jobs/{job_id}", headers=headers)
        )
        last_body = body
        if body["status"] == "done":
            return body
        if body["status"] == "failed":
            raise RuntimeError(f"background job {job_id} failed: {body}")
        await asyncio.sleep(0.5)
    raise TimeoutError(f"background job {job_id} did not finish: {last_body}")


async def _main() -> None:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=30) as api:
        seed = await seed_operator_emulator_wms(api)
        seller = seed.sellers["seller_a"]
        headers = seed.admin_headers

        role_logins: dict[str, dict[str, str]] = {}
        role_password = "password123"
        for role_name, packaging in (("operator", True), ("operator_no_packaging", False)):
            email = f"fbs-e2e-{role_name}-{seed.tenant_id}@example.com"
            account = await _require(
                await api.post("/auth/staff-accounts", headers=headers, json={"email": email}),
                expected=(201,),
            )
            await _require(
                await api.patch(
                    f"/auth/staff-accounts/{account['id']}/permissions",
                    headers=headers,
                    json={
                        "settings": False,
                        "mp_shipments": False,
                        "reception": False,
                        "cells": False,
                        "inventory": False,
                        "packaging": packaging,
                    },
                )
            )
            await _require(
                await api.post(
                    "/auth/set-initial-password",
                    json={"email": email, "password": role_password},
                )
            )
            role_logins[role_name] = {"email": email, "password": role_password}

        # A short login is deliberately included for typing on a handheld scanner
        # or a small emulator keyboard.  The tenant prefix keeps repeated fresh
        # demo databases independent without relying on a global fixed account.
        mobile_email = f"mobile-{seed.tenant_id.hex[:8]}@example.com"
        mobile_account = await _require(
            await api.post(
                "/auth/staff-accounts",
                headers=headers,
                json={"email": mobile_email},
            ),
            expected=(201,),
        )
        await _require(
            await api.patch(
                f"/auth/staff-accounts/{mobile_account['id']}/permissions",
                headers=headers,
                json={
                    "settings": False,
                    "mp_shipments": False,
                    "reception": False,
                    "cells": False,
                    "inventory": False,
                    "packaging": True,
                },
            )
        )
        await _require(
            await api.post(
                "/auth/set-initial-password",
                json={"email": mobile_email, "password": "mobile123"},
            )
        )
        role_logins["mobile"] = {"email": mobile_email, "password": "mobile123"}

        seller_email = f"fbs-e2e-seller-{seed.tenant_id}@example.com"
        await _require(
            await api.post(
                "/auth/seller-accounts",
                headers=headers,
                json={"seller_id": str(seller.seller_id), "email": seller_email},
            ),
            expected=(201,),
        )
        await _require(
            await api.post(
                "/auth/set-initial-password",
                json={"email": seller_email, "password": role_password},
            )
        )
        role_logins["seller"] = {"email": seller_email, "password": role_password}

        stock_sync = await _require(
            await api.post(
                f"/operations/fbs-sellers/{seller.seller_id}/stocks/sync",
                headers=headers,
                json={"wb_warehouse_id": WB_WAREHOUSE_ID},
            ),
            expected=(200, 202),
        )
        if "id" in stock_sync:
            await _wait_job(api, headers, stock_sync["id"])

        async with httpx.AsyncClient(base_url=EMULATOR_BASE, timeout=30) as emulator:
            admin_headers = {"X-Admin-Token": EMULATOR_ADMIN_TOKEN}
            created: dict[str, list[dict[str, Any]]] = {}
            for route, chrt_id, barcode in (
                ("warehouse_sc", 111001, "2000000000011"),
                ("pvz", 111005, "2000000000015"),
                ("kiz", 111002, "2000000000012"),
            ):
                created[route] = []
                for index in range(2):
                    payload = await _require(
                        await emulator.post(
                            "/__admin/orders",
                            headers=admin_headers,
                            params={
                                "seller": "seller_a",
                                "count": 1,
                                "warehouse_id": WB_WAREHOUSE_ID,
                                "chrt_id": chrt_id,
                            },
                        )
                    )
                    if payload["created"] != 1 or not payload["orders"]:
                        raise RuntimeError(f"emulator did not create {route} order: {payload}")
                    created[route].append(
                        {
                            "wb_order_id": int(payload["orders"][0]["id"]),
                            "chrt_id": chrt_id,
                            "barcode": barcode,
                            "created_at_wb": payload["orders"][0]["createdAt"],
                        }
                    )
                    if index == 0:
                        await asyncio.sleep(1.05)

        order_sync = await _require(
            await api.post(
                "/operations/fbs-orders/sync",
                headers=headers,
                json={"seller_id": str(seller.seller_id)},
            ),
            expected=(202,),
        )
        await _wait_job(api, headers, order_sync["id"])

        worklist = await _require(
            await api.get(
                "/operations/fbs-orders/worklist",
                headers=headers,
                params={"seller_id": str(seller.seller_id), "status_group": "new", "limit": 200},
            )
        )
        by_wb = {int(item["wb_order_id"]): item for item in worklist["items"]}
        for route_items in created.values():
            if len({item["created_at_wb"] for item in route_items}) != len(route_items):
                raise RuntimeError("dynamic WB orders must have distinct createdAt values")
            for item in route_items:
                row = by_wb.get(item["wb_order_id"])
                if row is None:
                    raise RuntimeError(
                        f"dynamic WB order {item['wb_order_id']} missing from WMS worklist"
                    )
                if row["selection_blockers"]:
                    raise RuntimeError(
                        f"dynamic WB order {item['wb_order_id']} is blocked: "
                        f"{row['selection_blockers']}"
                    )
                item["wms_order_id"] = row["id"]

        # The browser flow starts from loose orders, while the mobile client starts
        # from the supply worklist.  Create two independent, untouched supplies so
        # an operator can complete the whole scanner-first flow and still has a
        # clean second attempt available without reseeding the database.
        mobile_supplies: list[dict[str, Any]] = []
        for index, item in enumerate(created["warehouse_sc"], start=1):
            workspace = await _require(
                await api.post(
                    "/operations/fbs-supplies/from-orders",
                    headers=headers,
                    json={
                        "name": f"Мобильная демо-поставка {index}",
                        "order_ids": [item["wms_order_id"]],
                        "planned_delivery_type": "warehouse_sc",
                        "idempotency_key": f"mobile-demo-{seed.tenant_id}-{index}",
                    },
                ),
                expected=(201,),
            )
            mobile_order = workspace["orders"][0]
            mobile_supplies.append(
                {
                    "supply_id": workspace["supply"]["id"],
                    "name": workspace["supply"]["name"],
                    "status": workspace["supply"]["status"],
                    "location_code": seed.storage_location_code,
                    "product_barcode": item["barcode"],
                    "order_sticker": mobile_order["sticker"]["code"],
                    "order_scan": mobile_order["sticker"]["code"]
                    or str(item["wb_order_id"]),
                    "wb_order_id": item["wb_order_id"],
                }
            )

        result = {
            "api_base": API_BASE,
            "emulator_base": EMULATOR_BASE,
            "emulator_admin_token": EMULATOR_ADMIN_TOKEN,
            "seller_key": "seller_a",
            "seller_token": seller.token,
            "seller_id": str(seller.seller_id),
            "tenant_id": str(seed.tenant_id),
            "warehouse_id": str(seed.warehouse_id),
            "location_code": seed.storage_location_code,
            "login": {"email": seed.admin_email, "password": seed.admin_password},
            "role_logins": role_logins,
            "orders": created,
            "mobile_demo": {
                "base_url": "http://10.0.2.2:18080/",
                "login": role_logins["mobile"],
                "instructions": [
                    "Откройте WB FBS и выберите демо-поставку.",
                    "Нажмите «Начать работу».",
                    "В подборе отсканируйте location_code, затем product_barcode.",
                    "В упаковке отсканируйте order_scan.",
                    "В передаче создайте короб, выберите его и снова отсканируйте order_scan.",
                    "Проверьте поставку и подтвердите передачу в локальный WB-эмулятор.",
                ],
                "supplies": mobile_supplies,
            },
            "stock_sync": stock_sync,
            "order_sync": order_sync,
        }
        sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(_main())

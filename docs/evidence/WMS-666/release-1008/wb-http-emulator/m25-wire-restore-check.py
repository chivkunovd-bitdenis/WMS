"""Bounded real-client WB wire proof against the local HTTP receiver."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx


BASE = "http://127.0.0.1:16709"
OUT = Path(__file__).with_name("m25-wire-restore-delete-pass.json")


async def main() -> None:
    timeout = httpx.Timeout(20)
    async with httpx.AsyncClient(timeout=timeout) as client:
        reset_receiver = await client.post("http://127.0.0.1:16710/reset-state")
        reset_receiver.raise_for_status()
        seeded = await client.post(f"{BASE}/seed", json={"codes": 4, "multi": False})
        seeded.raise_for_status()
        fixture = seeded.json()
        auth = fixture["headers"]
        token = auth.get("Authorization") or auth.get("authorization")
        assert token and token.startswith("Bearer ")
        order_id = fixture["order_ids"][0]
        supply_id = fixture["supply_id"]

        async def api(path: str, method: str = "GET", **kwargs):
            response = await client.request(method, f"{BASE}/proxy/{path.lstrip('/')}", headers=auth, **kwargs)
            response.raise_for_status()
            return response.json() if response.content else None

        before = (await client.get(f"{BASE}/snapshot")).json()
        available = [code["cis"] for code in before["codes"] if code["status"] == "available"]
        assert len(available) >= 2
        workspace = await api(f"/operations/fbs-supplies/{supply_id}/workspace")
        wb_order_id = next(int(row["wb_order_id"]) for row in workspace["orders"] if row["id"] == order_id)
        accepted_cis, rejected_cis = available[:2]

        validation = await api(
            "/operations/fbs-orders/kiz/validate", "POST", json={"order_id": order_id, "value": accepted_cis}
        )
        assert validation.get("ok") is True
        first_commit = await api(
            "/operations/fbs-orders/kiz/commit",
            "POST",
            json={
                "pairs": [{"order_id": order_id, "value": accepted_cis, "confirmed": True}],
                "idempotency_key": "wms666-m25-first-wire-bind",
                "scan_no_wb_wait": False,
            },
        )
        first_receiver = (await client.get("http://127.0.0.1:16710/state")).json()
        OUT.write_text(
            json.dumps(
                {
                    "phase": "first-bind",
                    "fixture": {"supply_id": supply_id, "order_id": order_id, "wb_order_id": wb_order_id},
                    "available_codes": available,
                    "validation": validation,
                    "first_commit": first_commit,
                    "receiver": first_receiver,
                },
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

        configured = await client.post(
            f"{BASE}/configure-wb-rejection", json={"order_id": order_id, "cis_code": rejected_cis}
        )
        configured.raise_for_status()
        configure = configured.json()
        assert configure["outcome"] == "rejected"
        replacement_validation = await api(
            "/operations/fbs-orders/kiz/validate",
            "POST",
            json={"order_id": order_id, "value": rejected_cis},
        )
        assert replacement_validation.get("ok") is True
        rejected_commit = await api(
            "/operations/fbs-orders/kiz/commit",
            "POST",
            json={
                "pairs": [{"order_id": order_id, "value": rejected_cis, "confirmed": True}],
                "idempotency_key": "wms666-m25-refused-replacement",
                "scan_no_wb_wait": False,
            },
        )

        after = (await client.get(f"{BASE}/snapshot")).json()
        receiver = (await client.get("http://127.0.0.1:16710/state")).json()
        current = next(mark for mark in after["markings"] if mark["order_id"] == order_id)
        writes = [row for row in receiver["requests"] if row.get("orderId") == wb_order_id]
        put_rows = [row for row in writes if row["method"] == "PUT"]
        delete_rows = [row for row in writes if row["method"] == "DELETE"]
        assert current["cis"] == accepted_cis
        assert receiver["sgtinByOrder"][str(wb_order_id)] == accepted_cis
        assert [row["body"]["sgtins"] for row in put_rows] == [[accepted_cis], [rejected_cis], [accepted_cis]]
        assert [row["status"] for row in put_rows] == [204, 409, 204]
        assert len(delete_rows) == 2
        assert all(row["method"] == "DELETE" and row["status"] == 204 for row in delete_rows)
        assert [row["path"] for row in delete_rows] == [
            f"/api/v3/orders/{wb_order_id}/meta?key=sgtin",
            f"/api/v3/orders/{wb_order_id}/meta?key=sgtin",
        ]
        assert all(row["authorizationPresent"] for row in writes)
        assert after["stock"] == before["stock"]

        OUT.write_text(
            json.dumps(
                {
                    "classification": "real Wildberries client HTTP serialization to local synthetic loopback receiver; not live WB",
                    "product_sha": "7f493b4fbff9c4fa85f0c7f6b88f096ae7df85bc",
                    "fixture": {"supply_id": supply_id, "order_id": order_id, "wb_order_id": wb_order_id},
                    "before": {"markings": before["markings"], "available_codes": available},
                    "validation": validation,
                    "first_commit": first_commit,
                    "replacement_validation": replacement_validation,
                    "rejected_commit": rejected_commit,
                    "after": {"markings": after["markings"], "codes": after["codes"], "stock": after["stock"]},
                    "receiver": receiver,
                    "assertions": {
                        "same_exact_cis_restored_in_wms": current["cis"] == accepted_cis,
                        "same_exact_cis_restored_in_receiver": receiver["sgtinByOrder"][str(wb_order_id)] == accepted_cis,
                        "put_body_order": [row["body"]["sgtins"][0] for row in put_rows],
                        "put_status_order": [row["status"] for row in put_rows],
                        "delete_count": len(delete_rows),
                        "delete_status_order": [row["status"] for row in delete_rows],
                        "delete_paths": [row["path"] for row in delete_rows],
                        "stock_unchanged": after["stock"] == before["stock"],
                        "auth_header_present_only": all(row["authorizationPresent"] for row in writes),
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"result": "PASS", "path": str(OUT), "order_id": order_id, "wb_order_id": wb_order_id}))


if __name__ == "__main__":
    asyncio.run(main())

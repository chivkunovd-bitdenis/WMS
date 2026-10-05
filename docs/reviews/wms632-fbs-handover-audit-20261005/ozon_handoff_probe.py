"""Read-only product audit: isolated SQLite + existing Ozon fake fixtures.

Run from backend with PYTHONPATH=.; never connects to production or Ozon.
Observations describe current behavior, not a new acceptance contract.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

HERE = Path(__file__).resolve().parent
os.environ["WMS_TEST_DATABASE_URL"] = f"sqlite+aiosqlite:///{HERE / 'probe.sqlite'}"
os.environ["WMS_TEST_DATA_DIR"] = str(HERE / "probe-data")

from tests.conftest import _reset_database
from app.db.session import SessionLocal, engine
from app.models.fbs_order import FbsOrder, FbsOrderProduct, FbsOrderProductReservation
from app.models.fbs_supply import FbsSupply
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.services import fbs_shipment_service as shipment
from app.services.inventory_service import update_fbs_order_reservation
from app.services.marketplace_provider import (
    FakeMarketplaceTransport, MarketplaceProviderError, OzonMarketplaceProvider,
)
from sqlalchemy import func, select
from tests.test_fbs_ozon_lane import (
    _ozon_handoff_responses, _seed_ozon_supply_case, _seed_ready_for_handoff,
)


async def scenario(kind: str) -> dict:
    await _reset_database()
    async with SessionLocal() as session:
        tenant, _, _, product, order, supply = await _seed_ozon_supply_case(session, packed=True)
        assert supply is not None
        await _seed_ready_for_handoff(session, order, supply, product)
        await update_fbs_order_reservation(session, order, reserve=True)
        await session.commit()
        tenant_id, product_id, order_id, supply_id = tenant.id, product.id, order.id, supply.id

        async def snapshot() -> dict:
            # Independent reader proves a commit, rather than ORM memory/flush.
            async with SessionLocal() as reader:
                stock = await reader.scalar(select(func.sum(InventoryBalance.quantity)).where(
                    InventoryBalance.product_id == product_id))
                reservations = await reader.scalar(select(func.sum(FbsOrderProductReservation.quantity))
                    .join(FbsOrderProduct).where(FbsOrderProduct.order_id == order_id))
                moves = list(await reader.scalars(select(InventoryMovement.quantity_delta).where(
                    InventoryMovement.product_id == product_id,
                    InventoryMovement.movement_type == "fbs_shipment")))
                operations = list(await reader.scalars(select(FbsWbOperation).where(
                    FbsWbOperation.local_entity_id == supply_id)))
                s = await reader.get(FbsSupply, supply_id)
                o = await reader.get(FbsOrder, order_id)
                return {"stock": stock, "reserved": reservations or 0, "expense_deltas": moves,
                        "supply_status": s.status, "reserve_status": o.reserve_status,
                        "operations": [{"state": op.state, "error_code": op.error_code,
                            "approved": (op.request_summary_json or {}).get(
                                "ozon_handoff_progress", {}).get("carriage_approved")}
                            for op in operations]}

        responses = _ozon_handoff_responses()
        responses["/v1/carriage/get"] = {"carriage_id": 901, "status": "formed"}
        errors = {}
        if kind == "document_failure":
            errors["/v2/posting/fbs/act/get-barcode"] = MarketplaceProviderError("ozon", 503, {})
        elif kind == "definite_rejection":
            errors["/v1/carriage/approve"] = MarketplaceProviderError("ozon", 400, {})
        elif kind == "lost_create":
            errors["/v1/carriage/create"] = MarketplaceProviderError("ozon", 503, {})
        elif kind == "lost_approve_formed":
            errors["/v1/carriage/approve"] = MarketplaceProviderError("ozon", 503, {})
        transport = FakeMarketplaceTransport(endpoint_responses=responses, errors=errors,
            endpoint_response_queues={"/v1/carriage/get": [{"carriage_id": 901, "status": "new"}]})
        provider = OzonMarketplaceProvider(transport=transport)
        result = {"scenario": kind, "before": await snapshot(), "attempts": []}
        for index in range(2):
            if index and kind in {"document_failure", "lost_create", "lost_approve_formed"}:
                transport.errors.clear()
            try:
                await shipment.deliver_supply(session, tenant_id, supply_id, AsyncMock(),
                    idempotency_key=kind if kind == "success" else f"{kind}-{index}",
                    actor_user_id=None, ozon_provider=provider)
                outcome = "returned_success"
            except shipment.FbsShipmentError as exc:
                outcome = exc.code
            result["attempts"].append({"outcome": outcome, **await snapshot()})
        result["endpoint_calls"] = [path for path, _ in transport.endpoint_calls]
        return result


async def main() -> None:
    # Fail closed on any unmocked HTTP request, including background publication.
    with patch("httpx.AsyncClient.send", side_effect=AssertionError("Network forbidden in audit")), \
         patch("app.services.inventory_service.schedule_seller_stock_publish"):
        results = [await scenario(kind) for kind in (
            "success", "definite_rejection", "document_failure", "lost_create", "lost_approve_formed")]
    await engine.dispose()
    (HERE / "ozon-probe-results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

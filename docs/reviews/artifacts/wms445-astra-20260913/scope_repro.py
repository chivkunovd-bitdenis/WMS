"""Review-only reproduction; run from backend with PYTHONPATH=. Python."""
import asyncio
import sys
import json
import uuid

from tests import conftest
from tests.test_fbs_worklist_query_count import _setup_ff_admin_with_stock
from tests.fbs_seed_helpers import seed_fbs_warehouse_binding, DEFAULT_WB_WAREHOUSE_ID
from app.db.session import SessionLocal, engine
from app.main import create_app
from app.models.user import User
from app.models.ff_staff_permissions import FfStaffPermissions
from app.core.roles import FULFILLMENT_STAFF
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from httpx import ASGITransport, AsyncClient


async def main():
    await conftest._reset_database()
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        headers, seller_a, warehouse, product, _, ids_a = await _setup_ff_admin_with_stock(client)
        me = (await client.get("/auth/me", headers=headers)).json()
        seller_b_response = await client.post("/sellers", headers=headers, json={"name": "Review seller B"})
        assert seller_b_response.status_code == 201
        seller_b = uuid.UUID(seller_b_response.json()["id"])
        async with SessionLocal() as session:
            user = await session.get(User, uuid.UUID(me["id"]))
            # The real effective-seller dependency returns this user's seller_id.
            user.seller_id = seller_a
            user.role = FULFILLMENT_STAFF
            session.add(FfStaffPermissions(user_id=user.id, can_packaging=True))
            a = await session.get(FbsOrder, ids_a[0])
            await seed_fbs_warehouse_binding(session, tenant_id=a.tenant_id, seller_id=seller_b, wms_warehouse_id=warehouse)
            b = FbsOrder(tenant_id=a.tenant_id, seller_id=seller_b, warehouse_id=warehouse,
                product_id=product, marketplace="wb", wb_order_id=999111,
                wb_nm_id=900100, wb_chrt_id=777001, wb_barcode=a.wb_barcode,
                wb_warehouse_id=DEFAULT_WB_WAREHOUSE_ID, status="new", supplier_status="new",
                created_at_wb=a.created_at_wb, deadline_at=a.deadline_at,
                mapping_status="mapped", reserve_status="reserved")
            session.add(b)
            sa = FbsSupply(tenant_id=a.tenant_id, seller_id=seller_a, warehouse_id=warehouse,
                marketplace="wb", wb_supply_id="review-a", name="Review A", status="assembling", delivery_type="warehouse_sc")
            sb = FbsSupply(tenant_id=a.tenant_id, seller_id=seller_b, warehouse_id=warehouse,
                marketplace="wb", wb_supply_id="review-b", name="Review B", status="assembling", delivery_type="warehouse_sc")
            session.add_all([sa, sb])
            await session.commit()
            b_id, sb_id = str(b.id), str(sb.id)
        base = {"marketplace": "wb", "status_group": "tsd_working"}
        scoped = await client.get("/operations/fbs-orders/worklist", headers=headers, params=base)
        explicit = await client.get("/operations/fbs-orders/worklist", headers=headers, params={**base, "seller_id": str(seller_b)})
        supplies = await client.get("/operations/fbs-supplies/worklist", headers=headers, params={"marketplace":"wb", "status_group":"active"})
        assert scoped.status_code == explicit.status_code == supplies.status_code == 200
        result = {
            "default_order_scope_is_A": {x["id"] for x in scoped.json()["items"]} == {str(ids_a[0])},
            "explicit_seller_B_bypasses_A_scope": b_id in {x["id"] for x in explicit.json()["items"]},
            "default_active_supplies_leaks_B_into_A_scope": sb_id in {x["id"] for x in supplies.json()["items"]},
        }
        if "--expect-fixed" in sys.argv:
            async with SessionLocal() as session:
                user = await session.get(User, uuid.UUID(me["id"]))
                user.seller_id = None
                await session.commit()
            all_orders = await client.get("/operations/fbs-orders/worklist", headers=headers, params=base)
            all_supplies = await client.get("/operations/fbs-supplies/worklist", headers=headers, params={"marketplace":"wb", "status_group":"active"})
            narrow_orders = await client.get("/operations/fbs-orders/worklist", headers=headers, params={**base,"seller_id":str(seller_b)})
            narrow_supplies = await client.get("/operations/fbs-supplies/worklist", headers=headers, params={"marketplace":"wb", "status_group":"active","seller_id":str(seller_b)})
            assert {x["id"] for x in all_orders.json()["items"]} == {str(ids_a[0]),b_id}
            assert {x["id"] for x in all_supplies.json()["items"]} == {str(sa.id),sb_id}
            assert {x["id"] for x in narrow_orders.json()["items"]} == {b_id}
            assert {x["id"] for x in narrow_supplies.json()["items"]} == {sb_id}
            print("Unscoped fulfillment_staff: both sellers visible; explicit seller narrows both lists: PASS")
        print(json.dumps(result, indent=2))
        expected = [True, False, False] if "--expect-fixed" in sys.argv else [True, True, True]
        assert list(result.values()) == expected, "Reproduction differs from requested expectation"
    await conftest._reset_database()
    await engine.dispose()


asyncio.run(main())

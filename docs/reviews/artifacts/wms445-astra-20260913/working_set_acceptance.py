"""C16-C20 service/HTTP acceptance only; no device/marketplace claims.

Run from backend: PYTHONPATH=. <venv-python> ../docs/reviews/artifacts/wms445-astra-20260913/working_set_acceptance.py
Uses the existing isolated conftest SQLite, no live fixture or real marketplace.
"""
import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests import conftest
from tests.test_fbs_worklist_query_count import _setup_ff_admin_with_stock
from app.db.session import SessionLocal, engine
from app.main import create_app
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.user import User
from app.models.ff_staff_permissions import FfStaffPermissions
from app.core.roles import FULFILLMENT_STAFF
from app.services.ozon_fbs_sync_service import _apply_status
from app.services.wb_marketplace_orders_service import _apply_wb_status_to_order
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select


async def main():
    await conftest._reset_database()
    result = {}
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        headers, seller, warehouse, product, _, seed_ids = await _setup_ff_admin_with_stock(client)
        foreign_headers, _, *_ = await _setup_ff_admin_with_stock(client)
        identity = (await client.get("/auth/me", headers=headers)).json()
        now = datetime.now(UTC)
        rows = {}
        expected = {"wb": set(), "ozon": set()}
        serial = 0
        async with SessionLocal() as session:
            initial = await session.get(FbsOrder, seed_ids[0])
            initial.status = "done"
            tenant = initial.tenant_id
            employee = await session.get(User, uuid.UUID(identity["id"]))
            employee.role = FULFILLMENT_STAFF
            employee.seller_id = None
            session.add(FfStaffPermissions(user_id=employee.id, can_packaging=True))
            def make(market, status, supplier, tag, age=30):
                nonlocal serial
                serial += 1
                row = FbsOrder(tenant_id=tenant, seller_id=seller, warehouse_id=warehouse,
                    product_id=None, marketplace=market, wb_order_id=9451000+serial,
                    external_order_id=f"acceptance-{serial}" if market=="ozon" else None,
                    wb_nm_id=900100, wb_chrt_id=777001, wb_barcode=f"REVIEW-{serial}",
                    wb_warehouse_id=initial.wb_warehouse_id, status=status,
                    supplier_status=supplier, created_at_wb=now-timedelta(days=age, seconds=serial),
                    deadline_at=now-timedelta(days=1), mapping_status="missing",
                    reserve_status="skipped_no_product")
                session.add(row)
                rows[(market,tag)] = row
                return row
            supply = FbsSupply(tenant_id=tenant, seller_id=seller, warehouse_id=warehouse,
                marketplace="ozon", name="Review active Ozon", status="assembling", delivery_type="warehouse_sc")
            session.add(supply)
            await session.flush()
            for market in ("wb","ozon"):
                for status in ("new","in_supply","assembling","packed","in_delivery","sorted","done","cancelled","defect","external_processing"):
                    row=make(market,status,None if status=="new" else "awaiting_deliver",status)
                    if market=="ozon" and status in ("in_supply","assembling","packed"):
                        row.supply_id=supply.id
                make(market,"new","new","explicit-new",age=60)
                make(market,"new","confirm","supplier-confirm")
                for i in range(105):
                    make(market,"done",None,f"history-{i}",age=500)
            await session.flush()
            for (market,tag), row in rows.items():
                if row.status in {"in_supply","assembling","packed"} or (row.status=="new" and row.supplier_status in (None,"new")):
                    expected[market].add(str(row.id))
            supply_id=str(supply.id)
            await session.commit()

        async def pages(market, auth=headers, **filters):
            items=[]; cursor=None; n=0
            while True:
                query={"marketplace":market,"status_group":"tsd_working","sort":"oldest","limit":2,**filters}
                if cursor: query["cursor"]=cursor
                response=await client.get("/operations/fbs-orders/worklist",headers=auth,params=query)
                assert response.status_code==200, response.status_code
                body=response.json(); items.extend(body["items"]); n+=1
                cursor=body["next_cursor"]
                if not cursor: return items,n
                assert n<20

        async with SessionLocal() as session:
            before=list((await session.execute(select(FbsOrder.id,FbsOrder.status,FbsOrder.supply_id).where(FbsOrder.tenant_id==tenant).order_by(FbsOrder.id))).all())
        for market in ("wb","ozon"):
            items,n=await pages(market)
            ids=[x["id"] for x in items]
            assert set(ids)==expected[market] and len(ids)==len(set(ids))==5
            assert ids[0]==str(rows[(market,"explicit-new")].id)
            assert len(items)==5 and n==3
            again,_=await pages(market)
            assert [x["id"] for x in again]==ids
            history=await client.get("/operations/fbs-orders/worklist",headers=headers,params={"marketplace":market,"limit":500})
            assert history.status_code==200 and len(history.json()["items"])>=117
            other,_=await pages(market,foreign_headers)
            assert not (set(ids)&{x["id"] for x in other})
            result[f"C16_C18_{market}"]={"working":len(ids),"pages":n,"older_history":105,"repeat_same_ids":True,"foreign_tenant_excluded":True}
        async with SessionLocal() as session:
            after=list((await session.execute(select(FbsOrder.id,FbsOrder.status,FbsOrder.supply_id).where(FbsOrder.tenant_id==tenant).order_by(FbsOrder.id))).all())
            assert after==before
        result["C16_reads_preserve_status_and_supply_links"]=True
        active=await client.get("/operations/fbs-supplies/worklist",headers=headers,params={"marketplace":"ozon","status_group":"active"})
        assert active.status_code==200 and supply_id in {x["id"] for x in active.json()["items"]}

        # Real saved-status application routines, no mocked classification.
        async with SessionLocal() as session:
            for market,tag,raw in [("wb","new","sold"),("wb","explicit-new","cancel"),
                                   ("ozon","new","delivered"),("ozon","explicit-new","cancelled"),
                                   ("ozon","supplier-confirm","awaiting_deliver")]:
                row=await session.get(FbsOrder,rows[(market,tag)].id)
                if market=="wb":
                    await _apply_wb_status_to_order(session,row,raw,actor_user_id=uuid.UUID(identity["id"]))
                else: await _apply_status(session,row,raw)
            for state in ("in_supply","assembling","packed"):
                row=await session.get(FbsOrder,rows[("ozon",state)].id)
                await _apply_status(session,row,"awaiting_deliver")
                assert row.status==state and str(row.supply_id)==supply_id
            await session.commit()
        for market in ("wb","ozon"):
            items,_=await pages(market)
            assert {x["id"] for x in items}=={str(rows[(market,x)].id) for x in ("in_supply","assembling","packed")}
        active=await client.get("/operations/fbs-supplies/worklist",headers=headers,params={"marketplace":"ozon","status_group":"active"})
        assert supply_id in {x["id"] for x in active.json()["items"]}
        result["C19_saved_status_refresh"]={"terminal_disappeared":True,"own_ozon_stages_kept":True,"active_supply_kept":True,"boundary":"status application routines, no external poll or delivery UI"}

        async with SessionLocal() as session:
            binding=await session.scalar(select(FbsWarehouseBinding).where(FbsWarehouseBinding.seller_id==seller,FbsWarehouseBinding.marketplace=="wb"))
            binding.served=False
            await session.commit()
        assert (await pages("wb"))[0]==[]
        assert len((await pages("ozon"))[0])==3
        async with SessionLocal() as session:
            binding=await session.scalar(select(FbsWarehouseBinding).where(FbsWarehouseBinding.seller_id==seller,FbsWarehouseBinding.marketplace=="wb"))
            binding.served=True; binding.is_active=False
            await session.commit()
        assert (await pages("wb"))[0]==[]
        async with SessionLocal() as session:
            binding=await session.scalar(select(FbsWarehouseBinding).where(FbsWarehouseBinding.seller_id==seller,FbsWarehouseBinding.marketplace=="wb"))
            binding.is_active=True; binding.stock_sync_enabled=False
            await session.commit()
        assert len((await pages("wb"))[0])==3
        result["C20_served_and_active"]={"served_false_hidden":True,"inactive_hidden":True,"restored_visible":True,"publication_disabled_visible":True,"ozon_unchanged":True}
        print(json.dumps(result,ensure_ascii=False,indent=2))
        Path(__file__).with_name("working-set-results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    await conftest._reset_database()
    await engine.dispose()


asyncio.run(main())

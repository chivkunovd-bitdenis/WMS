"""WMS-675: owner-authorized release of 25 exact already handed Ozon reserves.

Default is a read-only preflight. Explicit CLI argument apply performs one
transaction through the existing reservation service. No inventory correction,
shipment creation/conduction, billing, status override or credential management.
"""
import asyncio
import hashlib
import inspect
import json
import sys
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, text

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.services.inventory_service import lock_stock_product, update_fbs_order_reservation
from app.services.marketplace_account_service import MarketplaceAccountService
from app.services.ozon_marketplace_transport import HttpxOzonMarketplaceTransport
from app.services.ozon_provider_factory import build_ozon_provider, ozon_live_api_enabled
from app.services.fbs_stock_publish_service import drain_background_stock_publish_tasks

TENANT = uuid.UUID("b80a893b-ab87-42b6-8fd7-6d41502c900f")
SELLER = uuid.UUID("cf6d31c5-944b-4382-af34-636ca9aa8cc3")
WAREHOUSE = uuid.UUID("2d968c65-4a8d-414e-9076-0f201c2dba63")
OZON_WAREHOUSE = "1020005029530200"
TARGETS = [{'order_id': 'e6302b06-9bca-4588-b149-12623daa9829', 'posting': '0114193604-0125-1', 'position_id': 'be8079fc-ae88-47fe-8a7f-e00855f1ca80', 'product_id': '605bdc71-baae-43dd-9ed4-fb37e07906c0', 'sku_code': 'video.nanny3', 'quantity': 1, 'handover_at': '2026-09-26T16:05:29Z', 'ozon_sku': 1695134284, 'offer_id': 'video.nanny3'}, {'order_id': '734143f5-ef4d-4331-ae56-8daaeddf7787', 'posting': '0125183519-0046-1', 'position_id': '6176481c-3d9f-40d1-92af-ee91582ab508', 'product_id': '605bdc71-baae-43dd-9ed4-fb37e07906c0', 'sku_code': 'video.nanny3', 'quantity': 1, 'handover_at': '2026-09-29T13:36:44Z', 'ozon_sku': 1695134284, 'offer_id': 'video.nanny3'}, {'order_id': '0db0d2ae-e584-4423-8b9f-e9d10024ec6d', 'posting': '0131913206-0032-2', 'position_id': '6246737f-5fd7-4377-9934-f6427aea1f6c', 'product_id': '1a99998b-1576-4e7f-9f9a-cf9eaf14907e', 'sku_code': 'video.nanny', 'quantity': 1, 'handover_at': '2026-09-28T12:31:33Z', 'ozon_sku': 1586484429, 'offer_id': 'video.nanny'}, {'order_id': '423bbd7b-1489-488f-882d-e00149652af2', 'posting': '0139808168-0022-1', 'position_id': 'a5b65dd9-0720-4ad2-9cf7-adea9c260538', 'product_id': '605bdc71-baae-43dd-9ed4-fb37e07906c0', 'sku_code': 'video.nanny3', 'quantity': 1, 'handover_at': '2026-09-27T15:55:41Z', 'ozon_sku': 1695134284, 'offer_id': 'video.nanny3'}, {'order_id': 'd0917f4b-0685-4910-93de-f37f3a4935f1', 'posting': '0141981036-0114-1', 'position_id': '6bf34bb3-4ab2-4a57-ad9e-9b92fb031b73', 'product_id': '605bdc71-baae-43dd-9ed4-fb37e07906c0', 'sku_code': 'video.nanny3', 'quantity': 1, 'handover_at': '2026-09-27T15:55:28Z', 'ozon_sku': 1695134284, 'offer_id': 'video.nanny3'}, {'order_id': '01cd88d9-3489-4fe7-8ffb-a5dc152314c7', 'posting': '0165637921-0049-1', 'position_id': '00dc4215-9f2c-43c9-aabb-968ba7090bb2', 'product_id': '80fa2a1e-1974-4e6e-8497-2defd0176bd5', 'sku_code': 'sausage2', 'quantity': 1, 'handover_at': '2026-09-29T13:37:30Z', 'ozon_sku': 1589998415, 'offer_id': 'sausage2'}, {'order_id': '54383829-fe6c-4f42-b215-739272cf3eec', 'posting': '0169260701-0215-2', 'position_id': 'fe1ffe19-85e7-4521-b5fe-b6f458a85ebc', 'product_id': '80fa2a1e-1974-4e6e-8497-2defd0176bd5', 'sku_code': 'sausage2', 'quantity': 1, 'handover_at': '2026-09-25T15:14:46Z', 'ozon_sku': 1589998415, 'offer_id': 'sausage2'}, {'order_id': 'e8c8dd6e-1203-4a0e-a953-de04051da9a5', 'posting': '0171686966-0145-1', 'position_id': 'ec9d4980-b740-4799-ba32-64e392288be0', 'product_id': '2ccde129-ed49-44fd-8dcc-4dd092581e26', 'sku_code': 'doorBell', 'quantity': 1, 'handover_at': '2026-09-26T16:04:37Z', 'ozon_sku': 1697770458, 'offer_id': 'doorBell'}, {'order_id': 'c53ceb5a-c66f-4ae7-b446-73deedc8aa5f', 'posting': '0174652514-0267-1', 'position_id': '331a08ab-21a0-4a80-a2e4-c0a084d43d90', 'product_id': '4d7e4a3d-954e-48f6-94a3-45729f2654d0', 'sku_code': 'aqua.skreb', 'quantity': 1, 'handover_at': '2026-09-28T12:29:45Z', 'ozon_sku': 1586466682, 'offer_id': 'aqua.skreb'}, {'order_id': '97d9dd17-10b5-452b-a812-20f1bd7fafdb', 'posting': '0203781849-0078-2', 'position_id': '75330bf4-d12f-46ed-a73e-c6027a22b7fc', 'product_id': '2ccde129-ed49-44fd-8dcc-4dd092581e26', 'sku_code': 'doorBell', 'quantity': 1, 'handover_at': '2026-09-29T13:38:50Z', 'ozon_sku': 1697770458, 'offer_id': 'doorBell'}, {'order_id': '6e76c0f2-4b38-45b3-8aa7-a25187b2ec75', 'posting': '0207219544-0199-1', 'position_id': '84980fb8-c18f-4786-98fc-3b3a0ca15dc8', 'product_id': 'e68905ee-fdca-4888-84ff-53b096fe76ec', 'sku_code': 'pilka.mlk', 'quantity': 1, 'handover_at': '2026-09-27T15:55:57Z', 'ozon_sku': 1985199282, 'offer_id': 'pilka.mlk'}, {'order_id': 'a5df698f-4066-4ea1-bd31-18990ec96b89', 'posting': '0212749158-0018-1', 'position_id': 'a12cb5af-475f-4ed6-abc6-580bfabc3fca', 'product_id': '605bdc71-baae-43dd-9ed4-fb37e07906c0', 'sku_code': 'video.nanny3', 'quantity': 1, 'handover_at': '2026-09-28T12:29:56Z', 'ozon_sku': 1695134284, 'offer_id': 'video.nanny3'}, {'order_id': '7ce02fe2-d049-41ab-b96f-728878a5fbce', 'posting': '0221085415-0009-1', 'position_id': '6c625970-f1da-42eb-bda5-c99c9a9c1951', 'product_id': '2ccde129-ed49-44fd-8dcc-4dd092581e26', 'sku_code': 'doorBell', 'quantity': 1, 'handover_at': '2026-09-28T12:30:25Z', 'ozon_sku': 1697770458, 'offer_id': 'doorBell'}, {'order_id': 'c095d7fa-4178-4d15-a4fe-4fa86230ccc9', 'posting': '0253444292-0123-1', 'position_id': '5831dbf8-8cd8-47ec-bdc8-ebb601da7661', 'product_id': '605bdc71-baae-43dd-9ed4-fb37e07906c0', 'sku_code': 'video.nanny3', 'quantity': 1, 'handover_at': '2026-09-28T12:31:42Z', 'ozon_sku': 1695134284, 'offer_id': 'video.nanny3'}, {'order_id': 'c2bac876-ec0a-4c2c-b1b7-8baf8e1baa70', 'posting': '43864254-0655-1', 'position_id': '3eb5d53e-ec1d-477d-938b-c7899037c8d7', 'product_id': '4d7e4a3d-954e-48f6-94a3-45729f2654d0', 'sku_code': 'aqua.skreb', 'quantity': 1, 'handover_at': '2026-09-25T15:13:16Z', 'ozon_sku': 1586466682, 'offer_id': 'aqua.skreb'}, {'order_id': 'd6372675-eed4-46bb-ac75-3a5b551e2048', 'posting': '45611774-0390-2', 'position_id': '2f0cdf1e-4b0a-4b1a-abed-62bcee8c27e8', 'product_id': '1a99998b-1576-4e7f-9f9a-cf9eaf14907e', 'sku_code': 'video.nanny', 'quantity': 1, 'handover_at': '2026-09-26T16:05:45Z', 'ozon_sku': 1586484429, 'offer_id': 'video.nanny'}, {'order_id': '3d15e95f-4531-4cf3-adcc-60d8eb3ac31f', 'posting': '48722483-0070-1', 'position_id': '02f0b337-7837-4a60-b21e-3c1e804cedc5', 'product_id': '4d7e4a3d-954e-48f6-94a3-45729f2654d0', 'sku_code': 'aqua.skreb', 'quantity': 1, 'handover_at': '2026-09-29T13:36:08Z', 'ozon_sku': 1586466682, 'offer_id': 'aqua.skreb'}, {'order_id': '453aa624-c2eb-4c95-ad2a-0a7beb5cbabf', 'posting': '55561835-0071-1', 'position_id': 'b1e6a3be-460e-489b-b6d6-02a1d3c38949', 'product_id': '605bdc71-baae-43dd-9ed4-fb37e07906c0', 'sku_code': 'video.nanny3', 'quantity': 1, 'handover_at': '2026-09-29T13:36:44Z', 'ozon_sku': 1695134284, 'offer_id': 'video.nanny3'}, {'order_id': 'efbb7f1c-9e70-491c-a389-201e8c7072b8', 'posting': '69352819-0016-2', 'position_id': 'c6e23053-4441-48c1-86e3-3befa0e5467b', 'product_id': '2a8a003e-d165-41cc-9b23-78f6ca79e245', 'sku_code': 'sausage3', 'quantity': 1, 'handover_at': '2026-09-29T13:39:15Z', 'ozon_sku': 1591143882, 'offer_id': 'sausage3'}, {'order_id': 'e48c1dbf-23b5-4916-be9b-54d4cb5edc95', 'posting': '73297437-0150-1', 'position_id': '12bd53cf-805d-493e-9a98-20fbbb3e6b2f', 'product_id': '80fa2a1e-1974-4e6e-8497-2defd0176bd5', 'sku_code': 'sausage2', 'quantity': 1, 'handover_at': '2026-09-26T16:05:24Z', 'ozon_sku': 1589998415, 'offer_id': 'sausage2'}, {'order_id': 'ffd37970-1142-4ad6-977b-af9dbe07d20c', 'posting': '84535705-0073-1', 'position_id': '29a2c293-ca6c-467b-85ac-fd3a5c225490', 'product_id': '4d7e4a3d-954e-48f6-94a3-45729f2654d0', 'sku_code': 'aqua.skreb', 'quantity': 1, 'handover_at': '2026-09-29T13:38:21Z', 'ozon_sku': 1586466682, 'offer_id': 'aqua.skreb'}, {'order_id': '5e42d231-3428-4b7b-844a-e0c3c0207a11', 'posting': '85564490-0201-1', 'position_id': '57f5708c-3660-4394-ade6-8cbf3c89dd88', 'product_id': '1a99998b-1576-4e7f-9f9a-cf9eaf14907e', 'sku_code': 'video.nanny', 'quantity': 1, 'handover_at': '2026-09-25T15:14:09Z', 'ozon_sku': 1586484429, 'offer_id': 'video.nanny'}, {'order_id': '2c2832b4-35a8-4124-b57a-f217447a9a9b', 'posting': '90532535-0087-1', 'position_id': '1eddebef-f9cd-4fac-b5d6-518c78dd733b', 'product_id': '2ccde129-ed49-44fd-8dcc-4dd092581e26', 'sku_code': 'doorBell', 'quantity': 1, 'handover_at': '2026-09-29T13:37:04Z', 'ozon_sku': 1697770458, 'offer_id': 'doorBell'}, {'order_id': '75f03d26-5bc4-46c1-9685-1d5e0edb4383', 'posting': '93193998-0124-2', 'position_id': '794f4f70-a870-46b4-880d-77eced2b1c17', 'product_id': '80fa2a1e-1974-4e6e-8497-2defd0176bd5', 'sku_code': 'sausage2', 'quantity': 1, 'handover_at': '2026-09-27T15:55:46Z', 'ozon_sku': 1589998415, 'offer_id': 'sausage2'}, {'order_id': '6f5899b4-7f66-4a69-b5ac-ad0eeae85b9c', 'posting': '97810120-0801-1', 'position_id': '482b425f-fca4-409b-a06e-f0cce34565f6', 'product_id': '2ccde129-ed49-44fd-8dcc-4dd092581e26', 'sku_code': 'doorBell', 'quantity': 1, 'handover_at': '2026-09-27T15:56:04Z', 'ozon_sku': 1697770458, 'offer_id': 'doorBell'}]


def emit(value):
    print(json.dumps(value, ensure_ascii=False, default=str), flush=True)


async def snapshot(session):
    params = {"ids": [uuid.UUID(r["order_id"]) for r in TARGETS],
              "pids": sorted({uuid.UUID(r["product_id"]) for r in TARGETS}),
              "tenant": TENANT}
    queries = {
        "positions": "SELECT o.id,o.status,o.reserve_status,o.supply_id,op.id AS position_id,op.product_id,op.quantity,op.reserved_quantity,op.picked_quantity FROM fbs_orders o JOIN fbs_order_products op ON op.order_id=o.id WHERE o.id=ANY(:ids) AND o.tenant_id=:tenant ORDER BY o.id,op.id",
        "reserves": "SELECT r.id,r.order_product_id,r.product_id,r.warehouse_id,r.quantity FROM fbs_order_product_reservations r JOIN fbs_order_products op ON op.id=r.order_product_id WHERE op.order_id=ANY(:ids) AND r.tenant_id=:tenant ORDER BY r.id",
        "legacy": "SELECT id,fbs_order_id,product_id,quantity FROM fbs_order_reservations WHERE fbs_order_id=ANY(:ids) AND tenant_id=:tenant ORDER BY id",
        "ledgers": "SELECT id,fbs_order_id,quantity,shipment_movement_id,ozon_positions_json FROM fbs_shipment_reversal_ledger WHERE fbs_order_id=ANY(:ids) AND tenant_id=:tenant ORDER BY id",
        "balances": "SELECT id,product_id,storage_location_id,quantity,quantity_unpacked,quantity_packed FROM inventory_balances WHERE product_id=ANY(:pids) AND tenant_id=:tenant ORDER BY id",
        "movement_totals": "SELECT product_id,count(*) AS rows,sum(quantity_delta) AS quantity FROM inventory_movements WHERE product_id=ANY(:pids) AND tenant_id=:tenant GROUP BY product_id ORDER BY product_id",
    }
    return {name: [dict(r) for r in (await session.execute(text(q),params)).mappings().all()] for name,q in queries.items()}


async def main():
    mode = sys.argv[1] if len(sys.argv)>1 else "check"
    assert mode in {"check","apply"}
    assert len(TARGETS)==25 and len({r["order_id"] for r in TARGETS})==25
    assert ozon_live_api_enabled()
    assert settings.ozon_seller_api_base.rstrip("/")=="https://api-seller.ozon.ru"
    assert hashlib.sha256(inspect.getsource(update_fbs_order_reservation).encode()).hexdigest() == "a31194ab56c71e82fecfe8cb6bc5e804a1575f2e6c7af03a70124ce61120b60c"
    started = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        client_id,api_key = await MarketplaceAccountService(session).stored_credentials(TENANT,SELLER)
        await session.rollback()
    cards=[]
    async with httpx.AsyncClient(timeout=30) as client:
        provider=build_ozon_provider()
        assert isinstance(provider.transport,HttpxOzonMarketplaceTransport)
        provider.transport=HttpxOzonMarketplaceTransport(client=client)
        for target in TARGETS:
            result=await provider.call(client_id=client_id,api_key=api_key,path="/v3/posting/fbs/get",payload={"posting_number":target["posting"],"with":{"analytics_data":False,"financial_data":False}})
            card=result["result"]
            assert card["posting_number"]==target["posting"]
            assert card["status"] in {"delivering","delivered"}
            assert str(card["delivery_method"]["warehouse_id"])==OZON_WAREHOUSE
            assert not card.get("related_postings") and not card.get("related_weight_postings")
            products=card["products"]
            assert len(products)==1 and int(products[0]["sku"])==target["ozon_sku"]
            assert products[0]["offer_id"]==target["offer_id"] and products[0]["quantity"]==1
            assert card["delivering_date"]==target["handover_at"]
            cards.append({"posting":target["posting"],"status":card["status"],"handover_at":card["delivering_date"],"sku":products[0]["sku"],"quantity":1})
    async with SessionLocal() as session:
        if mode=="check":
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        else:
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
            await session.execute(text("SET LOCAL statement_timeout = '30s'"))
        ids=[uuid.UUID(t["order_id"]) for t in TARGETS]
        stmt=select(FbsOrder).where(FbsOrder.id.in_(ids)).order_by(FbsOrder.id)
        if mode=="apply": stmt=stmt.with_for_update()
        orders=list((await session.scalars(stmt)).all())
        assert len(orders)==25
        mapping={r.id:r for r in orders}
        if mode=="apply":
            for pid in sorted({uuid.UUID(t["product_id"]) for t in TARGETS},key=str):
                assert await lock_stock_product(session,TENANT,pid) is not None
            await session.execute(select(FbsOrderProduct.id).where(FbsOrderProduct.order_id.in_(ids)).order_by(FbsOrderProduct.id).with_for_update())
        before=await snapshot(session)
        assert len(before["positions"])==25 and not before["legacy"] and not before["ledgers"]
        positions={r["id"]:r for r in before["positions"]}
        reserves={r["order_product_id"]:r for r in before["reserves"]}
        for target in TARGETS:
            oid=uuid.UUID(target["order_id"]);order=mapping[oid];position=positions[oid]
            assert order.tenant_id==TENANT and order.seller_id==SELLER and order.warehouse_id==WAREHOUSE
            assert order.marketplace=="ozon" and order.external_order_id==target["posting"] and order.supply_id is None
            assert order.status in {"in_delivery","done"}
            assert position["position_id"]==uuid.UUID(target["position_id"])
            assert position["product_id"]==uuid.UUID(target["product_id"])
            assert position["quantity"]==1 and position["picked_quantity"]==0
            reserve=reserves.get(position["position_id"])
            if reserve:
                assert reserve["warehouse_id"]==WAREHOUSE and reserve["product_id"]==position["product_id"]
                assert reserve["quantity"]==position["reserved_quantity"]==1
            else:
                assert position["reserved_quantity"]==0 and order.reserve_status=="released"
        receipt={"stage":"preflight","mode":mode,"at":datetime.now(timezone.utc),"cards":cards,"before":before,"service_sha256":hashlib.sha256(inspect.getsource(update_fbs_order_reservation).encode()).hexdigest()}
        emit(receipt)
        if mode=="check":
            await session.rollback();return
        assert (datetime.now(timezone.utc)-started).total_seconds()<120
        for order in orders:
            if positions[order.id]["position_id"] in reserves:
                await update_fbs_order_reservation(session,order,reserve=False)
        await session.flush()
        after=await snapshot(session)
        assert not after["reserves"] and not after["legacy"] and not after["ledgers"]
        assert all(r["reserved_quantity"]==0 and r["reserve_status"]=="released" for r in after["positions"])
        assert after["balances"]==before["balances"] and after["movement_totals"]==before["movement_totals"]
        assert [(r["id"],r["status"],r["supply_id"]) for r in after["positions"]]==[(r["id"],r["status"],r["supply_id"]) for r in before["positions"]]
        emit({"stage":"commit_start","reserve_units_released":sum(r["quantity"] for r in before["reserves"]),"after":after})
        await session.commit()
        emit({"stage":"committed","at":datetime.now(timezone.utc),"reserve_units_released":sum(r["quantity"] for r in before["reserves"]),"inventory_delta":0})
    await drain_background_stock_publish_tasks()
    emit({"stage":"finished","at":datetime.now(timezone.utc)})


if __name__=="__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        emit({"stage":"error","error_type":type(exc).__name__,"readback_required_before_retry":True})
        raise SystemExit(2)

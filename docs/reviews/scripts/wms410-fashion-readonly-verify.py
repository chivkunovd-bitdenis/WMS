"""WMS-410: independent DB and read-only WB verification after root operation."""
import asyncio
import json
import sys
import uuid
from collections import defaultdict
from datetime import UTC, datetime

import httpx
from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.fbs_stock_sync_service import _resolve_marketplace_api_token
from app.services.wildberries_client import fetch_marketplace_stocks

TENANT = uuid.UUID("7b98a8aa-c03c-4649-9677-a645be45c622")
SELLER = uuid.UUID("77b66021-25e9-4127-8c01-b8408eccde37")
OWN_ON = {2115687, 2103525, 2115694, 2157148}
OWN_OFF = {1865709, 2035877}

async def main():
    assert sys.argv[1:] == ["--root-operation-done"]
    async with SessionLocal() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        params = {"tenant": TENANT, "seller": SELLER}
        summary = dict((await session.execute(text("""
            SELECT count(*) AS products,
              count(*) FILTER (WHERE fbs_stock_sync_enabled) AS wb_on,
              count(*) FILTER (WHERE coalesce(fbs_ozon_stock_sync_enabled,fbs_stock_sync_enabled)) AS ozon_effective_on,
              count(*) FILTER (WHERE fbs_ozon_stock_sync_enabled=false) AS selected_off,
              count(*) FILTER (WHERE fbs_ozon_stock_sync_enabled IS NULL AND NOT fbs_stock_sync_enabled) AS legacy_off
            FROM products WHERE tenant_id=:tenant AND seller_id=:seller
        """), params)).mappings().one())
        assert summary == {"products":5425,"wb_on":0,"ozon_effective_on":0,"selected_off":34,"legacy_off":5391}, summary
        bindings = [dict(x) for x in (await session.execute(text("""
            SELECT id,marketplace,wb_warehouse_id,served,stock_sync_enabled
            FROM fbs_warehouse_bindings WHERE tenant_id=:tenant AND seller_id=:seller
        """), params)).mappings()]
        assert {int(x["wb_warehouse_id"]) for x in bindings} == OWN_ON | OWN_OFF
        assert all(x["marketplace"] == "wb" for x in bindings)
        assert all(bool(x["served"]) == (int(x["wb_warehouse_id"]) in OWN_ON)
                   and bool(x["stock_sync_enabled"]) == (int(x["wb_warehouse_id"]) in OWN_ON)
                   for x in bindings)
        rows = [dict(x) for x in (await session.execute(text("""
            SELECT b.wb_warehouse_id,i.chrt_id,i.product_id,i.last_target_amount,
                   i.last_confirmed_amount,i.status,i.last_error_code
            FROM fbs_stock_sync_items i
            JOIN products p ON p.id=i.product_id
            JOIN fbs_warehouse_bindings b ON b.id=i.binding_id
            WHERE p.tenant_id=:tenant AND p.seller_id=:seller
              AND b.tenant_id=:tenant AND b.seller_id=:seller
              AND p.fbs_ozon_stock_sync_enabled=false
              AND b.served AND b.stock_sync_enabled AND b.marketplace='wb'
            ORDER BY b.wb_warehouse_id,i.chrt_id
        """), params)).mappings()]
        assert len(rows) == 136, len(rows)
        assert len({str(x["product_id"]) for x in rows}) == 34
        db_nonzero = [x for x in rows if x["last_confirmed_amount"] not in (None,0)]
        assert not db_nonzero, db_nonzero
        grouped=defaultdict(list)
        for row in rows:
            warehouse=int(row["wb_warehouse_id"])
            assert warehouse in OWN_ON
            grouped[warehouse].append(int(row["chrt_id"]))
        token = await _resolve_marketplace_api_token(session,TENANT,SELLER)
        await session.rollback()
    readbacks=[]
    async with httpx.AsyncClient() as client:
        for warehouse,chrt_ids in grouped.items():
            fetched=await fetch_marketplace_stocks(client,api_token=token,warehouse_id=warehouse,chrt_ids=chrt_ids)
            amounts={x.chrt_id:x.amount for x in fetched}
            missing=[x for x in chrt_ids if x not in amounts]
            nonzero=[{"chrt_id":x,"amount":amounts[x]} for x in chrt_ids if x in amounts and amounts[x]!=0]
            result={"warehouse_id":warehouse,"requested":len(chrt_ids),"returned":len(fetched),"missing":missing,"nonzero":nonzero,"zero":sum(x in amounts and amounts[x]==0 for x in chrt_ids)}
            readbacks.append(result)
            print("READBACK="+json.dumps(result),flush=True)
            await asyncio.sleep(0.2)
    success = all(not row["missing"] and not row["nonzero"] for row in readbacks)
    result={"result":"PASS" if success else "FAIL","checked_at":datetime.now(UTC).isoformat(),"summary":summary,
      "bindings_flags_unchanged":True,"served_sync_items":len(rows),"db_positive":0,
      "db_confirmed_zero":sum(x["last_confirmed_amount"]==0 for x in rows),
      "db_unconfirmed":sum(x["last_confirmed_amount"] is None for x in rows),
      "db_status_counts":{status:sum(x["status"]==status for x in rows) for status in sorted({x["status"] for x in rows})},
      "db_positive_targets":sum((x["last_target_amount"] or 0)>0 for x in rows),
      "db_error_codes":{code:sum(x["last_error_code"]==code for x in rows) for code in sorted({x["last_error_code"] for x in rows if x["last_error_code"]})},
      "marketplace_readbacks":readbacks,
      "scope":"All current sync items of 34 explicitly disabled products on four served WB bindings; historical 64-item manifest was not persisted.",
      "method":"DB read-only transaction; standard read-only WB POST/chrtIds; no stock PUT, sync or other mutations"}
    print("RESULT="+json.dumps(result,ensure_ascii=False),flush=True)

if __name__ == "__main__":
    asyncio.run(main())

"""Independent read-only stock and active Ozon order comparison after release."""
import asyncio
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
import httpx
from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.marketplace_account_service import MarketplaceAccountService
from app.services.ozon_provider_factory import build_ozon_provider
from app.services.ozon_marketplace_transport import HttpxOzonMarketplaceTransport
from app.services.fbs_stock_availability_service import fbs_stock_breakdown_by_product
T=uuid.UUID('b80a893b-ab87-42b6-8fd7-6d41502c900f')
S=uuid.UUID('cf6d31c5-944b-4382-af34-636ca9aa8cc3')
W=uuid.UUID('2d968c65-4a8d-414e-9076-0f201c2dba63')
OW='1020005029530200'
async def main():
    async with SessionLocal() as s:
        await s.execute(text('SET TRANSACTION READ ONLY'))
        products=[dict(x) for x in (await s.execute(text("SELECT p.id,p.sku_code,l.external_sku,l.external_offer_id FROM products p JOIN product_marketplace_links l ON l.product_id=p.id WHERE p.tenant_id=:t AND p.seller_id=:s AND l.marketplace='ozon' AND l.is_active ORDER BY p.sku_code"),{'t':T,'s':S})).mappings().all()]
        cid,key=await MarketplaceAccountService(s).stored_credentials(T,S)
        await s.rollback()
    async with httpx.AsyncClient(timeout=30) as client:
        provider=build_ozon_provider();assert isinstance(provider.transport,HttpxOzonMarketplaceTransport)
        provider.transport=HttpxOzonMarketplaceTransport(client=client)
        active=await provider.fetch_orders(client_id=cid,api_key=key)
        active=[{'posting':x['posting_number'],'status':x['status'],'in_process_at':x.get('in_process_at'),'products':[{k:p.get(k) for k in ('sku','offer_id','quantity')} for p in x.get('products',[])]} for x in active if str(x.get('delivery_method',{}).get('warehouse_id'))==OW]
        stocks=[];cursor=''
        for _ in range(5):
            raw=await provider.call(client_id=cid,api_key=key,path='/v2/product/info/stocks-by-warehouse/fbs',payload={'sku':[x['external_sku'] for x in products],'limit':100,'cursor':cursor})
            stocks.extend(x for x in raw['products'] if str(x['warehouse_id'])==OW)
            if not raw.get('has_next'):break
            cursor=raw['cursor']
        else:raise RuntimeError('pagination')
    async with SessionLocal() as s:
        await s.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        breakdown=await fbs_stock_breakdown_by_product(s,T,W,[x['id'] for x in products])
        orders=[dict(x) for x in (await s.execute(text("SELECT o.id,o.external_order_id,o.status,o.reserve_status,p.sku_code,op.quantity,op.reserved_quantity FROM fbs_orders o JOIN fbs_order_products op ON op.order_id=o.id JOIN products p ON p.id=op.product_id WHERE o.tenant_id=:t AND o.seller_id=:s AND (op.reserved_quantity>0 OR o.external_order_id=ANY(:postings)) ORDER BY o.external_order_id"),{'t':T,'s':S,'postings':[x['posting'] for x in active]})).mappings().all()]
        await s.rollback()
    byoffer={x['offer_id']:x for x in stocks}
    comparison=[{'article':x['sku_code'],'wms':asdict(breakdown[x['id']]),'ozon':{k:byoffer[x['external_offer_id']][k] for k in ('present','reserved','free_stock')}} for x in products]
    print(json.dumps({'at':datetime.now(timezone.utc),'comparison':comparison,'active_ozon':active,'current_wms_orders':orders},ensure_ascii=False,default=str))
if __name__=='__main__':
    try:asyncio.run(main())
    except Exception as exc:
        print(json.dumps({'error_type':type(exc).__name__}));raise SystemExit(2)

"""Isolated WMS-363 emulator fixture; never connects to a client database."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ['DATABASE_URL'] = f'sqlite+aiosqlite:///{HERE / "emulator.sqlite"}'
os.environ['WMS_DATA_DIR'] = str(HERE / 'fixture-data')
os.environ['JWT_SECRET_KEY'] = 'wms363-isolated-emulator-test-value-only'
os.environ['WMS_ALLOW_PUBLIC_REGISTRATION'] = 'true'

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.db.session import engine, SessionLocal
from app.main import create_app
from app.models import Base
from app.models.user import User
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.fbs_supply import FbsSupply
from app.models.product import Product
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from tests.test_wms363_ozon_tsd import _create_seller_and_warehouse, _seed_order, _seed_supply
from app.services.tokens import decode_access_token
from datetime import UTC, datetime, timedelta
import uuid
import json

app = create_app()

async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        if await session.scalar(select(User).where(User.email == 'wms363-emulator@example.com')):
            return
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/auth/register', json={'organization_name':'WMS363 Emulator only','slug':'wms363-emulator','admin_email':'wms363-emulator@example.com','password':'Emulator363test'})
        assert response.status_code == 200
        token = response.json()['access_token']
        headers = {'Authorization':f'Bearer {token}'}
        tenant = uuid.UUID(decode_access_token(token)['tenant_id'])
        seller, warehouse = await _create_seller_and_warehouse(client, headers, 'emulator363')
        ids = {}
        for market in ['wb', 'ozon']:
            supply = await _seed_supply(tenant_id=tenant,seller_id=seller,warehouse_id=warehouse,marketplace=market,name=f'WMS363-{market}-unfinished')
            for i in range(2):
                oid = await _seed_order(tenant_id=tenant,seller_id=seller,warehouse_id=warehouse,marketplace=market,wb_order_id=(363000 if market=='wb' else 363100)+i,external_order_id=f'363-TEST-{i}' if market=='ozon' else None)
                async with SessionLocal() as session:
                    order = await session.get(FbsOrder,oid)
                    order.supply_id=supply
                    order.status='assembling'
                    order.created_at_wb=datetime.now(UTC)-timedelta(days=2-i)
                    order.deadline_at=datetime.now(UTC)+timedelta(hours=2 if i==0 else 24)
                    product=Product(tenant_id=tenant,seller_id=seller,name=f'{market} учебный товар {i+1}',sku_code=f'{market}-363-{i}',wb_barcode=f'363{1 if market=="wb" else 2}000{i}')
                    session.add(product);await session.flush()
                    order.product_id=product.id
                    order.wb_barcode=product.wb_barcode
                    if market=='ozon':
                        session.add(FbsOrderProduct(order_id=oid,product_id=product.id,position_index=0,quantity=2,ozon_sku=363100+i,picked_quantity=0))
                    await session.commit()
            ids[market]=str(supply)
        async with SessionLocal() as session:
            session.add(FbsWarehouseBinding(tenant_id=tenant,seller_id=seller,wms_warehouse_id=warehouse,marketplace='wb',wb_warehouse_id=501001,is_active=True,served=True))
            await session.commit()
        (HERE/'fixture-ids.json').write_text(json.dumps(ids,indent=2))

if __name__ == '__main__':
    asyncio.run(seed())
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=18083,access_log=False)

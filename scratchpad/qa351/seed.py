import asyncio
import json
import uuid
from runtime import QA, DB_NAME
from sqlalchemy import text
from app.db.session import SessionLocal, engine
from app.models import Base
from app.models.user import User
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.services.passwords import hash_password
from tests.test_fbs_stock_rule_service import _seed

async def main():
    async with engine.begin() as conn:
        assert await conn.scalar(text('select current_database()')) == DB_NAME
        assert await conn.scalar(text("select count(*) from information_schema.tables where table_schema='public'")) == 0
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        seed = await _seed(s, on_hand=10, wb_warehouse_ids=(501001,501002))
        seed.tenant.name='QA351 independent switches'
        seed.seller.name='QA351 WB + Ozon'
        seed.product.name='QA351 Legacy both — 10 physical'
        seed.product.fbs_percent=50
        seed.product.fbs_same_everywhere=False
        seed.bindings[1].marketplace='ozon'
        seed.bindings[1].external_warehouse_id='501002'
        s.add(User(id=uuid.uuid4(),tenant_id=seed.tenant.id,email='qa351@example.com',password_hash=hash_password('password123'),role='fulfillment_admin'))
        s.add(ProductMarketplaceLink(tenant_id=seed.tenant.id,seller_id=seed.seller.id,product_id=seed.product.id,marketplace='ozon',external_offer_id='QA351-OFFER',external_product_id='351',is_active=True))
        for b in seed.bindings:
            s.add(FbsBindingStockPool(tenant_id=seed.tenant.id,binding_id=b.id,product_id=seed.product.id,quantity=0,percent=50))
        await s.commit()
        (QA/'baseline.json').write_text(json.dumps(dict(tenant=str(seed.tenant.id),seller=str(seed.seller.id),product=str(seed.product.id),email='qa351@example.com',password='password123'),indent=2))
    await engine.dispose()
asyncio.run(main())

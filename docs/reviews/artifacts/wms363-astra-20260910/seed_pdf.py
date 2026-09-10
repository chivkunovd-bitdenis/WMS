"""One synthetic two-page Ozon asset in the isolated emulator database."""
import runpy
from pathlib import Path
import asyncio
runpy.run_path(str(Path(__file__).with_name('emulator_fixture.py')), run_name='fixture')
from app.models.fbs_print_asset import FbsPrintAsset
from app.services.fbs_print_asset_storage import order_sticker_relative_path, save_print_file, sha256_checksum
from app.models.fbs_order import FbsOrder
from app.models.user import User
from app.db.session import SessionLocal
from sqlalchemy import select
import fitz
async def main():
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email=='wms363-emulator@example.com'))
        assert user is not None
        order = await session.scalar(select(FbsOrder).where(FbsOrder.tenant_id==user.tenant_id,FbsOrder.marketplace=='ozon').order_by(FbsOrder.created_at_wb).limit(1))
        assert order is not None
        if await session.scalar(select(FbsPrintAsset).where(FbsPrintAsset.fbs_order_id==order.id)):
            return
        with fitz.open() as document:
            for index in [1,2]:
                page = document.new_page(width=164.4,height=113.4)
                page.insert_text((10,30),f'SYNTHETIC OZON {index}',fontsize=10)
            data=document.tobytes()
        path=save_print_file(order_sticker_relative_path(order.id,content_type='application/pdf'),data,content_type='application/pdf')
        session.add(FbsPrintAsset(tenant_id=user.tenant_id,seller_id=order.seller_id,fbs_order_id=order.id,fbs_supply_id=order.supply_id,kind='order_sticker',status='ready',content_type='application/pdf',storage_path=path,checksum=sha256_checksum(data)))
        order.sticker_status='ready'
        await session.commit()
        print('Prepared one synthetic two-page PDF label')
asyncio.run(main())

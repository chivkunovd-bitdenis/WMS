"""Upgrade the coordinator migration tree plus reviewed WMS444 revision in own PG."""
import json
import shutil
import uuid
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text, insert
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.models.seller import Seller
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.models.marketplace_unload import MarketplaceUnloadRequest, MarketplaceUnloadBox, MarketplaceUnloadBoxLine, MarketplaceUnloadPickAllocation

root=Path.cwd()
source=root.parent/'tsd-package-20260913/backend/alembic'
target=root/'.local-run/wms444-review-migration-tree'
assert not target.exists(), 'Use a new isolated migration-copy directory'
shutil.copytree(source,target)
shutil.copy2(root/'backend/alembic/versions/20260913_0306_wms444_mp_box_source.py',target/'versions')
cfg=Config(str(root/'backend/alembic.ini'))
cfg.set_main_option('script_location',str(target))
cfg.set_main_option('prepend_sys_path',str(root/'backend'))
url='postgresql+psycopg://deniscivkunov@localhost:5432/wms444_astra_upgrade_20260913'
engine=create_engine(url)
with engine.connect() as conn:
    assert conn.scalar(text('select current_database()'))=='wms444_astra_upgrade_20260913'
command.upgrade(cfg,'20260913_0305')
ids={k:uuid.uuid4() for k in ['tenant','warehouse','seller','product','location','request','box','allocation','boxline']}
with engine.begin() as c:
    c.execute(insert(Tenant.__table__).values(id=ids['tenant'],name='Review migration',slug='review-migration-'+ids['tenant'].hex[:8]))
    c.execute(insert(Warehouse.__table__).values(id=ids['warehouse'],tenant_id=ids['tenant'],name='Review',code='review'))
    c.execute(insert(Seller.__table__).values(id=ids['seller'],tenant_id=ids['tenant'],name='Review'))
    c.execute(insert(Product.__table__).values(id=ids['product'],tenant_id=ids['tenant'],seller_id=ids['seller'],name='Review',sku_code='review'))
    c.execute(insert(StorageLocation.__table__).values(id=ids['location'],tenant_id=ids['tenant'],warehouse_id=ids['warehouse'],code='review',barcode='review'))
    c.execute(insert(MarketplaceUnloadRequest.__table__).values(id=ids['request'],tenant_id=ids['tenant'],warehouse_id=ids['warehouse'],seller_id=ids['seller'],marketplace='wb',status='collecting'))
    c.execute(insert(MarketplaceUnloadBox.__table__).values(id=ids['box'],request_id=ids['request'],box_preset='60_40_40'))
    c.execute(insert(MarketplaceUnloadBoxLine.__table__).values(id=ids['boxline'],box_id=ids['box'],product_id=ids['product'],quantity=3))
    c.execute(insert(MarketplaceUnloadPickAllocation.__table__).values(id=ids['allocation'],request_id=ids['request'],product_id=ids['product'],storage_location_id=ids['location'],quantity=3))
command.upgrade(cfg,'head')
with engine.connect() as c:
    version=c.scalar(text('select version_num from alembic_version'))
    cols=c.execute(text("select table_name,is_nullable,column_default from information_schema.columns where table_name in ('marketplace_unload_box_lines','marketplace_unload_pick_allocations') and column_name='quantity_packed' order by table_name")).all()
    historic=[list(c.execute(text(f'select quantity, quantity_packed from {table}')).one()) for table in ['marketplace_unload_box_lines','marketplace_unload_pick_allocations']]
    print(json.dumps({'case':'full-chain-upgrade','version':version,'columns':[list(x) for x in cols],'historical':historic}))
    assert version=='20260913_0306' and historic==[[3,None],[3,None]]
command.upgrade(cfg,'head')
engine.dispose()

"""Run actual historical WMS query/helper functions on an in-memory SQLite DB.

Only synthetic rows. No WMS database, credentials, HTTP, Redis, or worker calls.
Run with existing backend venv Python; source comes from named Git revisions.
"""
import ast
import asyncio
import json
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import Boolean, DateTime, Integer, String, Uuid, and_, create_engine, exists, func, or_, select
from sqlalchemy.orm import DeclarativeBase, mapped_column, Session

class Base(DeclarativeBase):
    pass

class FbsOrder(Base):
    __tablename__ = 'orders'
    id = mapped_column(Uuid, primary_key=True)
    tenant_id = mapped_column(Uuid)
    seller_id = mapped_column(Uuid)
    marketplace = mapped_column(String)
    wb_warehouse_id = mapped_column(Integer)
    status = mapped_column(String)
    supplier_status = mapped_column(String)
    deadline_at = mapped_column(DateTime)
    created_at_wb = mapped_column(DateTime)

class FbsWarehouseBinding(Base):
    __tablename__ = 'bindings'
    id = mapped_column(Uuid, primary_key=True)
    tenant_id = mapped_column(Uuid)
    seller_id = mapped_column(Uuid)
    marketplace = mapped_column(String)
    wb_warehouse_id = mapped_column(Integer)
    is_active = mapped_column(Boolean)
    served = mapped_column(Boolean)

class AsyncRead:
    def __init__(self, session): self.session = session
    async def execute(self, stmt): return self.session.execute(stmt)

FUNCTIONS = {'_is_supplier_status_new', '_deadline_in_work_clause',
             '_deadline_expired_clause', '_supplier_new_clause', '_fetch_orders_page',
             'compute_selection_blockers', '_as_utc'}

async def check(revision):
    source = subprocess.check_output(['git','show',revision+':backend/app/services/fbs_worklist_service.py'],text=True)
    tree = ast.parse(source)
    selected = [node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in FUNCTIONS]
    module = ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*selected],type_ignores=[])
    env = dict(globals())
    for status in ['NEW','CANCELLED','DEFECT']:
        env['FBS_ORDER_STATUS_'+status] = status.lower()
    env.update(MAPPING_STATUS_MISSING='missing',RESERVE_STATUS_NOT_PUBLISHED='not_published',
               STATUS_GROUP_MAP={'new':frozenset({'new'}),'expired':frozenset({'new'})})
    exec(compile(ast.fix_missing_locations(module),revision,'exec'),env)
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    tid,sid,oid = uuid.uuid4(),uuid.uuid4(),uuid.uuid4()
    created = datetime(2026,9,25,10,3,19,tzinfo=UTC)
    with Session(engine) as db:
        binding = FbsWarehouseBinding(id=uuid.uuid4(),tenant_id=tid,seller_id=sid,marketplace='wb',
            wb_warehouse_id=2100731,is_active=True,served=True)
        db.add_all([binding,FbsOrder(id=oid,tenant_id=tid,seller_id=sid,marketplace='wb',wb_warehouse_id=2100731,
            status='new',supplier_status='new',deadline_at=created+timedelta(hours=120),created_at_wb=created)])
        db.commit()
        results=[]
        for age in [119,120,121,146.32,239]:
            now=created+timedelta(hours=age)
            counts={}
            for group in ['new','expired']:
                rows,_=await env['_fetch_orders_page'](AsyncRead(db),tid,seller_id=sid,marketplace='wb',
                    status_group=group,wb_warehouse_id=None,search=None,limit=100,cursor=None,server_now=now)
                counts[group]=len(rows)
            synthetic=SimpleNamespace(status='new',supplier_status='new',marketplace='wb',mapping_status='mapped',
                product_id=uuid.uuid4(),supply_id=None,order_products=[],reserve_status='reserved',warehouse_id=uuid.uuid4(),
                deadline_at=created+timedelta(hours=120))
            blockers=env['compute_selection_blockers'](synthetic,available_unpacked=10,server_now=now)
            results.append({'age_hours':age,**counts,'blockers':[b['code'] for b in blockers]})
        binding.served=False;db.commit()
        rows,_=await env['_fetch_orders_page'](AsyncRead(db),tid,seller_id=sid,marketplace='wb',status_group='expired',
            wb_warehouse_id=None,search=None,limit=100,cursor=None,server_now=created+timedelta(hours=146.32))
        return {'revision':revision,'served_true':results,'served_false_expired_count':len(rows)}

async def main():
    for revision in ['39efd0034834cdf9f51fd2214669300ccf9a028b','89680ae383cc2767a82cf88499cff503d266811a','addb225fb39676e2cafa87cd74ef52a0bc98386b','HEAD']:
        print(json.dumps(await check(revision),ensure_ascii=False))

asyncio.run(main())

"""GitHub-only C19 fixture server. No production environment or marketplace sockets."""
import os
import sys
from pathlib import Path

assert os.environ.get('GITHUB_ACTIONS') == 'true'
assert os.environ['DATABASE_URL'].endswith('/wms_test_662_c19')
sys.path[:0] = [str(Path.cwd() / 'backend'), str(Path.cwd() / 'backend/tests')]
import httpx
from fastapi import FastAPI
from app.db.session import engine, SessionLocal
from app.models import Base
from app.models.user import User
from app.api.deps import require_fbs_operator_access
from app.api.fbs_supplies import router
from test_wms662_observed_handoff import seed, external, sync, saved, shipped

app = FastAPI()
app.include_router(router)
case = api = user = None

async def fixture_user():
    return user
app.dependency_overrides[require_fbs_operator_access] = fixture_user

async def no_marketplace_socket(*args, **kwargs):
    raise AssertionError('C19 prohibits real external HTTP')
httpx.AsyncHTTPTransport.handle_async_request = no_marketplace_socket

@app.on_event('startup')
async def start():
    global case, api, user
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        case = await seed(session, count=2)
        user = User(tenant_id=case.tenant.id, role='fulfillment_admin',
                    email='fixture@invalid.example', password_hash='fixture-not-login')
        session.add(user)
        await session.commit()
    api = external(case)
    api.rows[case.orders[1].wb_order_id]['supplierStatus'] = 'confirm'

@app.get('/fixture')
async def fixture():
    return {'supply_id': str(case.supply.id), 'order_ids': [str(o.id) for o in case.orders]}

@app.post('/fixture/{phase}')
async def phase(phase: str):
    assert phase in {'partial', 'full'}
    if phase == 'full':
        api.rows[case.orders[1].wb_order_id]['supplierStatus'] = 'complete'
    await sync(case, api)
    state = await saved(case)
    expected = 1 if phase == 'partial' else 2
    assert shipped(state, case.products[0]) == expected
    assert (state.supply.delivered_at is not None) == (phase == 'full')
    assert len(state.supplies) == 1
    return {'phase': phase, 'supply_id': str(case.supply.id),
            'supply_status': state.supply.status,
            'delivered_at': str(state.supply.delivered_at) if state.supply.delivered_at else None,
            'shipped': shipped(state, case.products[0]),
            'stock': {str(k): v for k,v in state.stock.items()},
            'reserves': {str(k): v for k,v in state.reserves.items()},
            'orders': [{'id': str(o.id), 'wb_order_id': o.wb_order_id, 'status': o.status,
                        'movement_id': str(o.shipment_movement_id) if o.shipment_movement_id else None}
                       for o in state.orders.values()],
            'external_reads': api.calls,
            'synthetic_external_response': api.rows}

"""Audit runtime-only product mutants. Never alters source or test expectations."""
import os
import socket

def pytest_sessionstart(session):
    def deny_network(*args, **kwargs):
        raise OSError('audit plugin forbids real socket connection')
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    name = os.environ.get('WMS_AUDIT_MUTATION', '')
    async def nothing(*args, **kwargs):
        return None
    if name == 'drop_mapping':
        from app.services import wb_marketplace_orders_service as service
        service._map_product = nothing
    elif name == 'drop_supply_binding':
        from app.services import fbs_supply_service as service
        service._bind_orders_to_supply = nothing
    elif name == 'drop_pick_undo':
        from app.services import fbs_picking_service as service
        service._undo_wb_pick = nothing
    elif name == 'drop_cancel_release':
        from app.services import fbs_cancellation_service as service
        service._release_reservation = nothing
    elif name:
        raise RuntimeError('Unrecognized bounded audit mutation')
    print('WMS_AUDIT_PRODUCT_MUTATION=' + (name or 'none'))

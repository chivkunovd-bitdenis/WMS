"""Exact ArtMaks incident repair. Run inside production API; default rollback.

No WB mutations. Live WB done + exact order-set readback precedes DB mutation.
Preserves pick/undo history and markings. Uses existing shipment ledger/services.
"""
import asyncio
import json
import sys
import uuid
from collections import Counter
from datetime import UTC, datetime

import httpx
from sqlalchemy import select, text
from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.fbs_order_pick import FbsOrderPick, FbsOrderPickEvent
from app.models.fbs_supply import FbsSupply
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_wb_operation import FbsWbOperation
from app.models.inventory_balance import InventoryBalance
from app.services.fbs_shipment_source_service import FbsShipmentSourcePlan, FbsShipmentSourceResolution
from app.services.fbs_shipment_service import _write_off_delivered_orders_once
from app.services.document_event_service import record_document_event
from app.services.wildberries_credentials_service import get_decrypted_marketplace_token
from app.services.wildberries_fbs_client import fetch_marketplace_supply_details, fetch_marketplace_supply_order_ids

T = uuid.UUID('82b36645-8662-497f-9631-a0743994632c')
S = uuid.UUID('68dd641b-c5cc-4e0a-8057-015eca180d0e')
W = uuid.UUID('5740eda2-b353-4c98-9755-0f2df4e862bc')
SORT = uuid.UUID('9f3fbb36-2996-43bb-a2b8-4e7fe4ba9977')
EXPECTED = {'WB-GI-285910955': 358, 'WB-GI-285911018': 23}
MISSING_PICK_WB = 5916996766

async def main():
    apply = '--apply' in sys.argv
    async with SessionLocal() as s:
        await s.execute(text('SET TRANSACTION READ ONLY'))
        token = await get_decrypted_marketplace_token(s, T, S)
        assert token
        remote = {}
        async with httpx.AsyncClient(timeout=40) as client:
            for name, count in EXPECTED.items():
                detail = await fetch_marketplace_supply_details(client, api_token=token, supply_id=name, marketplace_api_base='https://marketplace-api.wildberries.ru')
                ids = await fetch_marketplace_supply_order_ids(client, api_token=token, supply_id=name, marketplace_api_base='https://marketplace-api.wildberries.ru')
                assert detail.done and detail.supply_id == name and len(ids) == count and len(set(ids)) == count
                remote[name] = set(ids)
        await s.rollback()
    async with SessionLocal() as s:
        await s.execute(text("SET LOCAL lock_timeout='8s'"))
        await s.execute(text("SET LOCAL statement_timeout='90s'"))
        supplies = list((await s.scalars(select(FbsSupply).where(FbsSupply.tenant_id == T, FbsSupply.seller_id == S, FbsSupply.wb_supply_id.in_(EXPECTED)).order_by(FbsSupply.id).with_for_update())).all())
        assert len(supplies) == 2 and all(x.warehouse_id == W for x in supplies)
        orders = list((await s.scalars(select(FbsOrder).where(FbsOrder.tenant_id == T, FbsOrder.seller_id == S, FbsOrder.supply_id.in_([x.id for x in supplies])).order_by(FbsOrder.id).with_for_update())).all())
        assert len(orders) == 381 and all(x.product_id and x.marketplace == 'wb' and x.status != 'cancelled' for x in orders)
        for su in supplies:
            assert {o.wb_order_id for o in orders if o.supply_id == su.id} == remote[su.wb_supply_id]
        ledgers = list((await s.scalars(select(FbsShipmentReversalLedger).where(FbsShipmentReversalLedger.fbs_order_id.in_([o.id for o in orders])).with_for_update())).all())
        if ledgers:
            assert len(ledgers) == 381 and all(x.shipment_movement_id and not x.reversed_at for x in ledgers), 'Partial/pre-existing reconciliation; stop'
            print(json.dumps({'mode': 'already_applied', 'ledger_count': 381}))
            await s.rollback()
            return
        products = {o.product_id for o in orders}
        # Lock all affected products and balances in stable order against other stock operations.
        await s.execute(text('SELECT id FROM products WHERE id = ANY(:ids) ORDER BY id FOR UPDATE'), {'ids': list(products)})
        balances = list((await s.scalars(select(InventoryBalance).where(InventoryBalance.tenant_id == T, InventoryBalance.product_id.in_(products)).order_by(InventoryBalance.id).with_for_update())).all())
        qty = {(b.product_id, b.storage_location_id, b.container_kind, b.container_id): b.quantity for b in balances}
        before_total = sum(qty.values())
        before_sorting = sum(v for k,v in qty.items() if k[1] == SORT)
        assert before_sorting == 363
        picks = list((await s.scalars(select(FbsOrderPick).where(FbsOrderPick.tenant_id == T, FbsOrderPick.fbs_order_id.in_([o.id for o in orders])).order_by(FbsOrderPick.picked_at))).all())
        by_order = {}
        for p in picks:
            by_order.setdefault(p.fbs_order_id, []).append(p)
        resolutions = {}
        modes = Counter()
        for o in orders:
            history = by_order.get(o.id, [])
            active = [p for p in history if p.undone_at is None]
            assert len(active) <= 1
            if active:
                p = active[0]
                assert p.product_id == o.product_id and p.inventory_movement_id is not None
                location, kind, container, mode = p.sorting_storage_location_id, None, None, 'legacy_sorting'
                assert location == SORT
            elif history:
                p = history[-1]
                assert p.product_id == o.product_id and p.inventory_movement_id is not None
                event = await s.scalar(select(FbsOrderPickEvent).where(FbsOrderPickEvent.pick_id == p.id, FbsOrderPickEvent.event_type == 'undone'))
                assert event is not None and (event.idempotency_key or '').startswith('artmaks-rescan-reset')
                location, kind, container, mode = p.source_storage_location_id, p.source_container_kind, p.source_container_id, 'manual_pick'
            else:
                assert o.wb_order_id == MISSING_PICK_WB
                location, kind, container, mode = SORT, None, None, 'forced_negative'
            key = (o.product_id, location, kind, container)
            available = qty.get(key, 0)
            negative = int(available < 1)
            assert negative == 0 or o.wb_order_id == MISSING_PICK_WB, ('Unexpected shortage', o.wb_order_id)
            qty[key] = available - 1
            modes[mode] += 1
            resolutions[o.id] = FbsShipmentSourceResolution(fbs_order_id=o.id, product_id=o.product_id, quantity=1, source_warehouse_id=W, storage_location_id=location, container_kind=kind, container_id=container, source_mode=mode, positive_quantity=1-negative, shortage_quantity=negative, negative_quantity=negative)
        assert dict(modes) == {'legacy_sorting': 363, 'manual_pick': 17, 'forced_negative': 1}, dict(modes)
        now = datetime.now(UTC)
        for su in supplies:
            selected = [o for o in orders if o.supply_id == su.id]
            operation = FbsWbOperation(tenant_id=T, seller_id=S, operation_kind='supply_delivery_reconciliation', idempotency_key='wms627:'+su.wb_supply_id, wb_object_id=su.wb_supply_id, wb_object_kind='supply', local_entity_type='fbs_supply', local_entity_id=su.id, state='confirmed', confirmed_at=now, request_summary_json={'task':'WMS-627','reason':'owner confirmed shipment; live WB done and exact composition; missing stock write-off'}, response_summary_json={'wb_done':True,'order_count':len(selected),'order_set_verified':True,'external_mutation':False})
            s.add(operation)
            await s.flush()
            plan = FbsShipmentSourcePlan(tenant_id=T, supply_warehouse_id=W, resolutions=tuple(resolutions[o.id] for o in selected))
            await _write_off_delivered_orders_once(s, su, selected, None, source_plan=plan, operation=operation)
            await record_document_event(s, tenant_id=T, document_type='fbs_supply', document_id=su.id, event_type='data_changed', source='system', actor_user_id=None, qty=len(selected), payload_json={'kind':'wms627_missing_shipment_writeoff_reconciled','wb_done_verified':True,'exact_order_count':len(selected),'preserved_pick_history':True,'operation_id':str(operation.id)}, idempotency_key='wms627:writeoff:'+su.wb_supply_id)
        await s.flush()
        after = dict((await s.execute(text('SELECT storage_location_id, SUM(quantity) FROM inventory_balances WHERE tenant_id=:t AND product_id=ANY(:p) GROUP BY storage_location_id'), {'t':T,'p':list(products)})).all())
        count = await s.scalar(select(text('count(*)')).select_from(FbsShipmentReversalLedger).where(FbsShipmentReversalLedger.fbs_order_id.in_([o.id for o in orders]),FbsShipmentReversalLedger.shipment_movement_id.is_not(None)))
        assert count == 381 and sum(after.values()) == before_total-381 and after[SORT] == -1
        result={'mode':'applied' if apply else 'rollback_verified','wb_order_counts':EXPECTED,'writeoff_count':count,'sources':dict(modes),'affected_products_total_before':before_total,'affected_products_total_after':sum(after.values()),'sorting_before':before_sorting,'sorting_after':after[SORT],'missing_initial_stock_order':MISSING_PICK_WB,'checked_at':now.isoformat()}
        if apply:
            await s.commit()
        else:
            await s.rollback()
        print(json.dumps(result,ensure_ascii=False))

asyncio.run(main())

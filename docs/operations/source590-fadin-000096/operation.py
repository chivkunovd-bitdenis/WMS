"""One-off owner source590 operation; run inside the existing production API.

Only this intake and WB binding are authorized. No application code is changed.
JSON output is captured in the permanent job worktree before any write.
"""
import asyncio
import dataclasses
import hashlib
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

logging.disable(logging.CRITICAL)

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_stock_sync_item import FbsStockSyncItem
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inbound_intake import InboundIntakeLine, InboundIntakeRequest
from app.models.product import Product
from app.services.fbs_seller_warehouse_service import list_seller_warehouses
from app.services.fbs_stock_rule_service import (
    FbsBindingRule, FbsRule, get_rule_views, publish_amounts_for_binding,
    set_rule_for_products,
)
from app.services.fbs_stock_sync_service import (
    _resolve_marketplace_api_token, sync_binding_stocks,
)
from app.services.marketplace_seller_lock_service import marketplace_seller_lock
from app.services.wildberries_client import fetch_marketplace_stocks

TENANT = uuid.UUID("7b98a8aa-c03c-4649-9677-a645be45c622")
SELLER = uuid.UUID("d1f26146-e99a-41af-9471-9c80ec990db3")
INTAKE = uuid.UUID("3dc35984-eb89-418b-9500-62ba0449e6e8")
BINDING = uuid.UUID("28654e42-481a-4b34-afbb-9118b305f792")
WB_WAREHOUSE = 2067199
PRODUCT_FIELDS = (
    "id", "tenant_id", "seller_id", "wb_vendor_code", "wb_size", "wb_chrt_id",
    "wb_barcode", "fbs_stock_sync_enabled", "fbs_stock_limit", "fbs_percent",
    "fbs_units_mode", "fbs_same_everywhere", "fbs_ozon_stock_sync_enabled",
)


def encode(value):
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [encode(v) for v in value]
    if isinstance(value, (uuid.UUID, datetime)):
        return str(value)
    return value


def digest(value):
    return hashlib.sha256(json.dumps(encode(value), sort_keys=True).encode()).hexdigest()


def emit(value):
    print(json.dumps(encode(value), ensure_ascii=False), flush=True)


async def snapshot(session, http, *, external=True):
    intake = await session.get(InboundIntakeRequest, INTAKE)
    assert intake and intake.tenant_id == TENANT and intake.seller_id == SELLER
    assert intake.display_number == "№000096"
    lines = list((await session.scalars(select(InboundIntakeLine).where(
        InboundIntakeLine.request_id == INTAKE).order_by(InboundIntakeLine.product_id))).all())
    ids = [line.product_id for line in lines]
    assert len(ids) == len(set(ids)) == 287
    products = list((await session.scalars(select(Product).where(
        Product.tenant_id == TENANT, Product.seller_id == SELLER).order_by(Product.id))).all())
    selected = [p for p in products if p.id in set(ids)]
    assert len(selected) == 287
    assert all(p.wb_chrt_id and p.wb_barcode for p in selected)
    chrts = [int(p.wb_chrt_id) for p in selected]
    assert len(set(chrts)) == len(chrts)
    assert all(sum(q.wb_chrt_id == p.wb_chrt_id for q in products) == 1 for p in selected)
    bindings = list((await session.scalars(select(FbsWarehouseBinding).where(
        FbsWarehouseBinding.tenant_id == TENANT,
        FbsWarehouseBinding.seller_id == SELLER).order_by(FbsWarehouseBinding.id))).all())
    binding = next(b for b in bindings if b.id == BINDING)
    assert binding.marketplace == "wb" and binding.wb_warehouse_id == WB_WAREHOUSE
    assert binding.is_active and binding.stock_sync_enabled
    assert binding.wms_warehouse_id == intake.warehouse_id
    assert not binding.lease_until or binding.lease_until < datetime.now(timezone.utc)
    pools = list((await session.scalars(select(FbsBindingStockPool).where(
        FbsBindingStockPool.tenant_id == TENANT,
        FbsBindingStockPool.binding_id.in_([b.id for b in bindings])
    ).order_by(FbsBindingStockPool.product_id, FbsBindingStockPool.binding_id))).all())
    prod_rows = [{f: getattr(p, f) for f in PRODUCT_FIELDS} for p in products]
    pool_rows = [{c.name: getattr(p, c.name) for c in p.__table__.columns} for p in pools]
    binding_rows = [{c.name: getattr(b, c.name) for c in b.__table__.columns} for b in bindings]
    views = await get_rule_views(session, TENANT, ids)
    result = {
        "snapshot_at": datetime.now(timezone.utc), "tenant_id": TENANT,
        "seller_id": SELLER, "intake_id": INTAKE, "wb_warehouse_id": WB_WAREHOUSE,
        "binding_id": BINDING, "intake_status": intake.status,
        "intake_created_at": intake.created_at, "intake_posted_at": intake.posted_at,
        "products_count": len(ids), "intake_actual_quantity": sum(l.actual_qty or 0 for l in lines),
        "selected_products": [p for p in prod_rows if p["id"] in set(ids)],
        "selected_pools": [p for p in pool_rows if p["product_id"] in set(ids)],
        "bindings": binding_rows, "views": views,
        "outside_products_count": len(products) - len(selected),
        "outside_products_hash": digest([p for p in prod_rows if p["id"] not in set(ids)]),
        "outside_pools_hash": digest([p for p in pool_rows if p["product_id"] not in set(ids)]),
        "other_effective_rules_hash": digest({pid: {bid: {
            "publish": v.publish, "mode": v.mode, "value": v.value,
            "units_configured": v.units_configured,
        } for bid, v in view.by_binding.items() if bid != BINDING}
            for pid, view in views.items()}),
    }
    if external:
        warehouses = await list_seller_warehouses(session, TENANT, SELLER, http)
        exact = [w for w in warehouses if w["name"] == "Лыткарино"]
        assert len(exact) == 1 and exact[0]["id"] == WB_WAREHOUSE
        result["warehouse"] = exact[0]
        token = await _resolve_marketplace_api_token(session, TENANT, SELLER)
        stocks = await fetch_marketplace_stocks(http, api_token=token,
            warehouse_id=WB_WAREHOUSE, chrt_ids=chrts)
        result["wb_read_at"] = datetime.now(timezone.utc)
        result["wb_stocks"] = {r.chrt_id: r.amount for r in stocks}
    return result, ids, selected, binding


async def main():
    phase = sys.argv[1]
    assert phase in {"preflight", "configure", "publish", "verify"}
    async with SessionLocal() as session, httpx.AsyncClient() as http:
        before, ids, selected, binding = await snapshot(session, http)
        if phase in {"preflight", "verify"}:
            if phase == "verify":
                before["calculated_amounts"] = await publish_amounts_for_binding(session, binding, selected)
            emit({"phase": phase, "snapshot": before})
            return
        if phase == "configure":
            emit({"phase": "before_configuration", "snapshot": before})
            # The regular scheduler publishes the entire seller. Capture that
            # intent in this one-off process and execute the existing publisher
            # separately with its product_ids filter, preserving owner scope.
            intents = []
            with patch("app.services.fbs_stock_rule_service.schedule_seller_stock_publish",
                       side_effect=lambda *args: intents.append(tuple(str(v) for v in args[1:]))):
                saved = await set_rule_for_products(session, TENANT, ids,
                    FbsRule(publish=None, publish_ozon=None, same_everywhere=False, percent=0,
                        by_binding={BINDING: FbsBindingRule(publish=True, mode="percent", value=100)},
                        by_binding_present=True))
            await session.close()
            async with SessionLocal() as reread:
                after, _, _, _ = await snapshot(reread, http, external=False)
            assert before["outside_products_hash"] == after["outside_products_hash"]
            assert before["outside_pools_hash"] == after["outside_pools_hash"]
            assert before["other_effective_rules_hash"] == after["other_effective_rules_hash"]
            for view in after["views"].values():
                rule = view.by_binding[BINDING]
                assert rule.publish and rule.mode == "percent" and rule.value == 100
            emit({"phase": "configured", "saved": saved, "captured_intents": intents, "snapshot": after})
        else:
            assert all(v.by_binding[BINDING].publish and
                v.by_binding[BINDING].mode == "percent" and
                v.by_binding[BINDING].value == 100 for v in before["views"].values())
            async with AsyncSession(bind=session.bind) as lock_session:
                async with marketplace_seller_lock(lock_session, SELLER, "wb", wait_timeout_sec=30) as acquired:
                    assert acquired
                    emit({"phase": "before_publication", "snapshot": before})
                    result = await sync_binding_stocks(session, TENANT, SELLER, binding, http,
                        product_ids=set(ids))
                    emit({"phase": "published", "result": result, "at": datetime.now(timezone.utc)})


try:
    asyncio.run(main())
except Exception as exc:
    emit({"phase": "failed", "error_type": type(exc).__name__, "error_code": getattr(exc, "code", None)})
    raise SystemExit(1)

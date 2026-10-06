"""Owner-authorized recovery of exactly the five existing Imperia boxes.

Default is read-only. --apply uses the installed normal application service,
original creation key and original actor. No shipping, stock or printer calls.
"""
import asyncio
import json
import sys
import uuid

import httpx
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.fbs_wb_operation import FbsWbOperation
from app.services import fbs_packing_box_service as packing
from app.services import fbs_shipment_pvz_service as cargo

TENANT = uuid.UUID("7b98a8aa-c03c-4649-9677-a645be45c622")
SELLER = uuid.UUID("d1f26146-e99a-41af-9471-9c80ec990db3")
SUPPLY = uuid.UUID("17141e9c-7f52-435c-887a-64efccb0760b")

async def main():
    async with SessionLocal() as session, httpx.AsyncClient(timeout=45) as client:
        supply = await packing._get_supply(session, TENANT, SUPPLY, for_update=True)
        assert supply.seller_id == SELLER and supply.wb_supply_id == "WB-GI-288882803"
        assert supply.status == "assembling" and supply.marketplace == "wb"
        boxes = await packing._load_boxes(session, TENANT, SUPPLY)
        assert len(boxes) == 5
        keys = {b.creation_idempotency_key for b in boxes}
        modes = {b.created_without_distribution for b in boxes}
        assert len(keys) == len(modes) == 1 and next(iter(keys))
        key = next(iter(keys))
        operation = await session.scalar(select(FbsWbOperation).where(
            FbsWbOperation.tenant_id == TENANT,
            FbsWbOperation.seller_id == SELLER,
            FbsWbOperation.local_entity_id == SUPPLY,
            FbsWbOperation.operation_kind == "cargo_places_create",
            FbsWbOperation.idempotency_key == key,
        ))
        assert operation is not None and operation.created_by_user_id is not None
        token = await cargo._require_marketplace_token(session, TENANT, SELLER, supply)
        remote_ids = await cargo.fetch_marketplace_supply_trbx_list(
            client, api_token=token, supply_id=supply.wb_supply_id)
        print(json.dumps({"phase":"preflight", "supply":supply.wb_supply_id,
            "local_boxes":len(boxes), "linked_boxes":sum(b.trbx_id is not None for b in boxes),
            "remote_ids":remote_ids, "original_operation":operation.state,
            "original_error":operation.error_code}), flush=True)
        if "--apply" not in sys.argv:
            await session.rollback()
            return
        assert not remote_ids, "Existing WB cargo places require reconciliation, never blind create"
        assert all(b.trbx_id is None for b in boxes)
        assert operation.state == "failed" and operation.error_code == "wb_upstream_error_404"
        result = await packing.create_boxes(session, TENANT, SUPPLY, 5, key, client,
            actor_user_id=operation.created_by_user_id,
            without_distribution=next(iter(modes)))
        await session.commit()
        rows = await cargo.list_cargo_places(session, TENANT, SUPPLY, client)
        await session.commit()
        print(json.dumps({"phase":"result", "local_boxes":len(result),
            "cargo_places":rows}, default=str), flush=True)

try:
    asyncio.run(main())
except Exception as exc:
    print(json.dumps({"phase":"error", "type":type(exc).__name__,
        "code":getattr(exc,"code",None), "status":getattr(exc,"status_code",None)}), flush=True)
    raise SystemExit(1)

"""Owner-authorized missing-label recovery, Imperia WB-GI-289512840 only."""

import asyncio
import json
import uuid

import httpx
from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.services.fbs_print_asset_service import request_supply_print_batch
from app.services.fbs_print_asset_storage import resolve_existing_storage_path
from sqlalchemy import select

TENANT = uuid.UUID("7b98a8aa-c03c-4649-9677-a645be45c622")


async def main():
    async with SessionLocal() as session:
        supplies = (
            (
                await session.execute(
                    select(FbsSupply).where(
                        FbsSupply.tenant_id == TENANT,
                        FbsSupply.wb_supply_id == "WB-GI-289512840",
                        FbsSupply.marketplace == "wb",
                        FbsSupply.status.notin_(["done", "cancelled"]),
                    )
                )
            )
            .scalars()
            .all()
        )
        targets = []
        for supply in supplies:
            orders = (
                (
                    await session.execute(
                        select(FbsOrder).where(
                            FbsOrder.tenant_id == TENANT,
                            FbsOrder.supply_id == supply.id,
                            FbsOrder.status != "cancelled",
                        )
                    )
                )
                .scalars()
                .all()
            )
            missing = [
                o.id
                for o in orders
                if not o.sticker_code
                or not o.sticker_file
                or not resolve_existing_storage_path(o.sticker_file).is_file()
            ]
            if missing:
                targets.append((supply.id, supply.wb_supply_id, missing))
        print(
            json.dumps(
                {
                    "preflight": [
                        {"supply": wb, "missing": len(ids)} for _, wb, ids in targets
                    ]
                }
            ),
            flush=True,
        )
        await session.rollback()
    async with httpx.AsyncClient(timeout=60) as client:
        for sid, wb, ids in targets:
            async with SessionLocal() as session:
                result = await request_supply_print_batch(
                    session,
                    TENANT,
                    sid,
                    kind="order_sticker",
                    order_ids=ids,
                    retry_missing=True,
                    http_client=client,
                )
                await session.commit()
                print(
                    json.dumps(
                        {
                            "supply": wb,
                            "requested": result.requested,
                            "ready": result.ready,
                            "missing": result.missing,
                            "failed": result.failed,
                            "errors": [e.code for e in result.order_errors],
                        }
                    ),
                    flush=True,
                )
    async with SessionLocal() as session:
        for sid, wb, ids in targets:
            orders = (
                (await session.execute(select(FbsOrder).where(FbsOrder.id.in_(ids))))
                .scalars()
                .all()
            )
            verified = sum(
                bool(
                    o.sticker_code
                    and o.sticker_file
                    and resolve_existing_storage_path(o.sticker_file)
                    .read_bytes()
                    .startswith(b"\x89PNG\r\n\x1a\n")
                )
                for o in orders
            )
            print(
                json.dumps(
                    {
                        "readback": wb,
                        "orders": len(orders),
                        "code_and_png_verified": verified,
                    }
                ),
                flush=True,
            )


asyncio.run(main())

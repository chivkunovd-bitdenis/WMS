# ruff: noqa: E402
# conftest must configure the isolated database before importing product modules.
"""Local-only audit harness: real API/DB, existing fake WB, no external transport."""

from __future__ import annotations

import asyncio
import base64
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, func, select

assert os.environ.get("WMS_TEST_DATABASE_URL", "").endswith("/wms_test_666_browser_proof")
from conftest import _reset_database, create_app
from test_fbs_order_tape_concurrency import seed_tape, stock_snapshot
from test_fbs_kiz import _patch_wb_acceptance

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderMarking, FbsOrderProduct, FbsOrderReservation
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.marking_code import MarkingCode
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.services.fbs_print_asset_service import _persist_order_sticker_bytes

patch = pytest.MonkeyPatch()
product_app = create_app()
client = httpx.AsyncClient(transport=httpx.ASGITransport(app=product_app), base_url="http://test")
seed = None
active_requests = 0


async def deny_external(*args, **kwargs):
    raise RuntimeError("Audit forbids every external HTTP transport")


patch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", deny_external)


@asynccontextmanager
async def lifespan(_app):
    yield
    await client.aclose()
    patch.undo()


app = FastAPI(lifespan=lifespan)


@app.post("/seed")
async def reset(request: Request):
    global seed
    options = await request.json()
    for _ in range(100):
        if active_requests == 0:
            break
        await asyncio.sleep(0.1)
    assert active_requests == 0, "Previous audit case still has active API requests"
    await _reset_database()
    seed = await seed_tape(client, patch, options.get("codes", 4))
    supply_ids = [str(seed.supply_id)]
    second_seller = None
    if options.get("multi"):
        response = await client.post(
            "/sellers", headers=seed.headers, json={"name": "Audit seller B"}
        )
        assert response.status_code == 201
        second_seller = uuid.UUID(response.json()["id"])
    async with SessionLocal() as session:
        if second_seller:
            order = await session.get(FbsOrder, seed.order_ids[1])
            old_product = await session.get(Product, order.product_id)
            product = Product(
                **{
                    c.name: getattr(old_product, c.name)
                    for c in Product.__table__.columns
                    if c.name not in {"id", "seller_id", "created_at", "updated_at"}
                }
            )
            product.seller_id = second_seller
            session.add(product)
            old_supply = await session.get(FbsSupply, seed.supply_id)
            task = PackagingTask(
                tenant_id=seed.tenant_id, warehouse_id=old_supply.warehouse_id, status="in_progress"
            )
            session.add(task)
            await session.flush()
            supply = FbsSupply(
                tenant_id=seed.tenant_id,
                seller_id=second_seller,
                warehouse_id=old_supply.warehouse_id,
                name="Audit supply B",
                status="assembling",
                delivery_type=old_supply.delivery_type,
                wb_supply_id="WB-AUDIT-B",
                packaging_task_id=task.id,
            )
            session.add(supply)
            await session.flush()
            line = await session.get(PackagingTaskLine, seed.line_id)
            line.qty_total = 1
            session.add(
                PackagingTaskLine(
                    task_id=task.id,
                    product_id=product.id,
                    storage_location_id=line.storage_location_id,
                    qty_total=1,
                    qty_suggested_packed=0,
                    qty_confirmed_packed=0,
                    qty_packed_in_task=0,
                    qty_marking_printed=0,
                    qty_marking_external=0,
                )
            )
            order.product_id, order.seller_id, order.supply_id = (
                product.id,
                second_seller,
                supply.id,
            )
            reservation = await session.scalar(
                select(FbsOrderReservation).where(FbsOrderReservation.fbs_order_id == order.id)
            )
            reservation.product_id = product.id
            session.add(
                InventoryBalance(
                    tenant_id=seed.tenant_id,
                    product_id=product.id,
                    storage_location_id=line.storage_location_id,
                    quantity=3,
                    quantity_unpacked=3,
                    quantity_packed=0,
                )
            )
            codes = list(
                (await session.scalars(select(MarkingCode).order_by(MarkingCode.cis_code))).all()
            )
            for code in codes[len(codes) // 2 :]:
                code.seller_id, code.product_id = second_seller, product.id
            supply_ids.append(str(supply.id))
        for index, order_id in enumerate(seed.order_ids):
            order = await session.get(FbsOrder, order_id)
            product = await session.get(Product, order.product_id)
            order.wb_barcode = product.wb_barcode = "460666AUDIT"
            order.sticker_code = f"AUDIT-STICKER-{index}"
            order.sticker_barcode = f"*AUDIT{index}"
            if options.get("stickers"):
                asset = FbsPrintAsset(
                    tenant_id=seed.tenant_id,
                    seller_id=order.seller_id,
                    kind="order_sticker",
                    fbs_order_id=order.id,
                    fbs_supply_id=order.supply_id,
                )
                _persist_order_sticker_bytes(
                    asset=asset,
                    order=order,
                    png_bytes=base64.b64decode(options["stickers"][index]),
                    sticker_code=order.sticker_code,
                    sticker_barcode=order.sticker_barcode,
                    fetched_at=datetime.now(UTC),
                )
                session.add(asset)
        if options.get("bare"):
            supply = await session.get(FbsSupply, seed.supply_id)
            assert supply and supply.packaging_task_id == seed.task_id
            supply.packaging_task_id = None
            await session.execute(
                delete(PackagingTaskLine).where(PackagingTaskLine.task_id == seed.task_id)
            )
            task = await session.get(PackagingTask, seed.task_id)
            if task is not None:
                await session.delete(task)
        await session.commit()
    reject_index = options.get("reject_order_index")
    if reject_index is not None:
        assert reject_index in range(len(seed.order_ids))
        async with SessionLocal() as session:
            rejected = await session.get(FbsOrder, seed.order_ids[reject_index])
            assert rejected is not None
            _patch_wb_acceptance(patch, reject_order_id=rejected.wb_order_id)
    return {
        "supply_id": str(seed.supply_id),
        "order_ids": list(map(str, seed.order_ids)),
        "supply_ids": supply_ids,
        "task_id": str(seed.task_id),
        "line_id": str(seed.line_id),
        "barcode": "460666AUDIT",
        "headers": seed.headers,
    }


@app.post("/seed-ozon")
async def reset_ozon(request: Request):
    global seed
    options = await request.json()
    for _ in range(100):
        if active_requests == 0:
            break
        await asyncio.sleep(0.1)
    assert active_requests == 0, "Previous proof case still has active API requests"
    await _reset_database()
    seed = await seed_tape(client, patch, options.get("codes", 4))
    position_ids: list[str] = []
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, seed.supply_id)
        assert supply
        supply.marketplace = "ozon"
        supply.wb_supply_id = None
        supply.name = "Synthetic Ozon posting set"
        first_order = await session.get(FbsOrder, seed.order_ids[0])
        assert first_order
        product = await session.get(Product, first_order.product_id)
        assert product
        product.requires_honest_sign = False
        for line in (
            await session.scalars(
                select(PackagingTaskLine).where(PackagingTaskLine.task_id == seed.task_id)
            )
        ).all():
            line.requires_honest_sign = False
        for index, order_id in enumerate(seed.order_ids):
            order = await session.get(FbsOrder, order_id)
            assert order
            order.marketplace = "ozon"
            order.external_order_id = f"OZON-PROOF-{index + 1}"
            order.wb_order_id = -666_100 - index
            order.required_meta_json = []
            order.optional_meta_json = []
            for position_index in range(2):
                position = FbsOrderProduct(
                    order_id=order.id,
                    product_id=order.product_id,
                    ozon_sku=6_661_000 + index * 10 + position_index,
                    offer_id=f"OZ-PROOF-{index + 1}-{position_index + 1}",
                    name=f"Synthetic Ozon product {position_index + 1}",
                    quantity=1,
                    position_index=position_index,
                    reserved_quantity=1,
                    picked_quantity=1,
                    provider_data_json={"sku": 6_661_000 + index * 10 + position_index, "quantity": 1},
                )
                session.add(position)
                await session.flush()
                position_ids.append(str(position.id))
        await session.commit()
    return {
        "supply_id": str(seed.supply_id),
        "order_ids": list(map(str, seed.order_ids)),
        "position_ids": position_ids,
        "supply_ids": [str(seed.supply_id)],
        "headers": seed.headers,
    }


@app.api_route("/proxy/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(path: str, request: Request):
    global active_requests
    assert seed is not None
    url = "/" + path + ("?" + request.url.query if request.url.query else "")
    active_requests += 1
    try:
        response = await client.request(
            request.method,
            url,
            headers={
                **seed.headers,
                "Content-Type": request.headers.get("Content-Type", "application/json"),
            },
            content=await request.body(),
        )
    finally:
        active_requests -= 1
    return Response(
        response.content,
        response.status_code,
        media_type=response.headers.get("Content-Type", "application/json"),
    )


@app.get("/idle")
async def idle():
    return {"active": active_requests}


@app.get("/snapshot")
async def snapshot():
    async with SessionLocal() as session:
        marks = list((await session.scalars(select(FbsOrderMarking))).all())
        codes = list((await session.scalars(select(MarkingCode))).all())
        orders = list((await session.scalars(select(FbsOrder))).all())
        supplies = list((await session.scalars(select(FbsSupply))).all())
        task_lines = list((await session.scalars(select(PackagingTaskLine))).all())
        assets = list((await session.scalars(select(FbsPrintAsset))).all())
        positions = list((await session.scalars(select(FbsOrderProduct))).all())
        balances = list(
            (
                await session.execute(
                    select(
                        InventoryBalance.id,
                        InventoryBalance.product_id,
                        InventoryBalance.quantity,
                        InventoryBalance.quantity_unpacked,
                        InventoryBalance.quantity_packed,
                    ).order_by(InventoryBalance.id)
                )
            ).all()
        )
        reservations = list(
            (
                await session.execute(
                    select(
                        FbsOrderReservation.id,
                        FbsOrderReservation.fbs_order_id,
                        FbsOrderReservation.product_id,
                        FbsOrderReservation.warehouse_id,
                        FbsOrderReservation.quantity,
                    ).order_by(FbsOrderReservation.id)
                )
            ).all()
        )
        movement_count = await session.scalar(select(func.count()).select_from(InventoryMovement))
        return jsonable_encoder(
            {
                "markings": [
                    {
                        "id": m.id,
                        "order_id": m.order_id,
                        "cis": m.value,
                        "code_id": m.marking_code_id,
                        "status": m.meta_status,
                    }
                    for m in marks
                ],
                "codes": [{"id": c.id, "cis": c.cis_code, "status": c.status} for c in codes],
                "orders": [
                    {
                        "id": o.id,
                        "supply_id": o.supply_id,
                        "marketplace": o.marketplace,
                        "external_order_id": o.external_order_id,
                        "pack_status": o.pack_status,
                        "packed_at": o.packed_at,
                    }
                    for o in orders
                ],
                "supplies": [
                    {
                        "id": s.id,
                        "marketplace": s.marketplace,
                        "packaging_task_id": s.packaging_task_id,
                    }
                    for s in supplies
                ],
                "task_lines": [
                    {
                        "id": line.id,
                        "task_id": line.task_id,
                        "product_id": line.product_id,
                        "qty_marking_printed": line.qty_marking_printed,
                        "qty_marking_external": line.qty_marking_external,
                        "qty_confirmed_packed": line.qty_confirmed_packed,
                        "qty_packed_in_task": line.qty_packed_in_task,
                    }
                    for line in task_lines
                ],
                "print_assets": [
                    {
                        "id": asset.id,
                        "order_id": asset.fbs_order_id,
                        "supply_id": asset.fbs_supply_id,
                        "kind": asset.kind,
                        "status": asset.status,
                        "applied_at": asset.applied_at,
                        "print_opened_at": asset.print_opened_at,
                    }
                    for asset in assets
                ],
                "positions": [
                    {
                        "id": position.id,
                        "order_id": position.order_id,
                        "product_id": position.product_id,
                        "ozon_sku": position.ozon_sku,
                        "quantity": position.quantity,
                        "position_index": position.position_index,
                    }
                    for position in positions
                ],
                "stock": {
                    "balances": [
                        {
                            "id": row.id,
                            "product_id": row.product_id,
                            "quantity": row.quantity,
                            "quantity_unpacked": row.quantity_unpacked,
                            "quantity_packed": row.quantity_packed,
                        }
                        for row in balances
                    ],
                    "reservations": [
                        {
                            "id": row.id,
                            "fbs_order_id": row.fbs_order_id,
                            "product_id": row.product_id,
                            "warehouse_id": row.warehouse_id,
                            "quantity": row.quantity,
                        }
                        for row in reservations
                    ],
                    "inventory_movement_count": movement_count,
                },
            }
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=16709, access_log=False)

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
from sqlalchemy import select

assert os.environ.get("WMS_TEST_DATABASE_URL", "") == "postgresql+psycopg_async://deniscivkunov@127.0.0.1:5432/wms_test_666_native_print_final_0c44"
from conftest import _reset_database, create_app
from test_fbs_order_tape_concurrency import seed_tape, stock_snapshot

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderMarking, FbsOrderReservation
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.marking_code import MarkingCode
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.services.fbs_print_asset_service import _persist_order_sticker_bytes
from app.services import fbs_kiz_service as kiz_service
from app.services import fbs_order_tape_print_service as tape_service
from app.services import fbs_marking_service
from app.services.wildberries_fbs_client import MarketplaceMetaDetail, MarketplaceOrderMetaRow

patch = pytest.MonkeyPatch()
product_app = create_app()
client = httpx.AsyncClient(transport=httpx.ASGITransport(app=product_app), base_url="http://test")
seed = None
active_requests = 0
synthetic_provider_readbacks: list[dict[str, object]] = []


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
    global seed, synthetic_provider_readbacks
    options = await request.json()
    for _ in range(100):
        if active_requests == 0:
            break
        await asyncio.sleep(0.1)
    assert active_requests == 0, "Previous audit case still has active API requests"
    await _reset_database()
    seed = await seed_tape(client, patch, options.get("codes", 4))
    synthetic_provider_readbacks = []
    # The tape test fixture installs a synthetic accepting WB sender and a
    # readback stub on fbs_marking_service. Share that exact sender with the
    # real KIZ commit API so a later operator-triggered status check reads the
    # same synthetic provider state without external HTTP.
    patch.setattr(
        kiz_service,
        "put_marketplace_order_meta",
        tape_service.marking_svc.put_marketplace_order_meta,
    )

    async def synthetic_accepted_readback(
        _client: object,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[MarketplaceOrderMetaRow]:
        """Return explicit local test-provider state; this is not a WB call."""
        del api_token, marketplace_api_base
        rows: list[MarketplaceOrderMetaRow] = []
        async with SessionLocal() as session:
            for wb_order_id in order_ids:
                order = await session.scalar(
                    select(FbsOrder).where(FbsOrder.wb_order_id == wb_order_id)
                )
                marking = None
                if order is not None:
                    marking = await session.scalar(
                        select(FbsOrderMarking)
                        .where(
                            FbsOrderMarking.order_id == order.id,
                            FbsOrderMarking.kind == "sgtin",
                        )
                        .order_by(FbsOrderMarking.created_at.desc(), FbsOrderMarking.id.desc())
                    )
                value = marking.value if marking is not None else None
                synthetic_provider_readbacks.append(
                    {"wb_order_id": wb_order_id, "cis": value, "decision": "accepted" if value else "missing"}
                )
                rows.append(
                    MarketplaceOrderMetaRow(
                        order_id=wb_order_id,
                        meta_details=(
                            (MarketplaceMetaDetail(key="sgtin", value=value, decision="accepted"),)
                            if value
                            else ()
                        ),
                        meta={"sgtin": [{"value": value, "checkStatus": "ok"}]} if value else {},
                    )
                )
        return rows

    patch.setattr(fbs_marking_service, "fetch_marketplace_orders_meta_batch", synthetic_accepted_readback)
    patch.setattr(kiz_service, "fetch_marketplace_orders_meta_batch", synthetic_accepted_readback)
    sticker_codes = options.get("sticker_codes") or [
        f"*AUDIT{index}" for index in range(len(seed.order_ids))
    ]
    assert len(sticker_codes) == len(seed.order_ids), "Each synthetic sticker must have one persisted QR value"
    supply_ids = [str(seed.supply_id)]
    second_seller = None
    if options.get("multi"):
        response = await client.post(
            "/sellers", headers=seed.headers, json={"name": "Audit seller B"}
        )
        assert response.status_code == 201
        second_seller = uuid.UUID(response.json()["id"])
    async with SessionLocal() as session:
        if options.get("bare"):
            bare_supply = await session.get(FbsSupply, seed.supply_id)
            assert bare_supply is not None
            bare_supply.packaging_task_id = None
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
            order.sticker_code = sticker_codes[index]
            order.sticker_barcode = sticker_codes[index]
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
                    sticker_code=sticker_codes[index],
                    sticker_barcode=sticker_codes[index],
                    fetched_at=datetime.now(UTC),
                )
                session.add(asset)
        await session.commit()
    return {
        "supply_id": str(seed.supply_id),
        "order_ids": list(map(str, seed.order_ids)),
        "supply_ids": supply_ids,
        "task_id": str(seed.task_id),
        "line_id": str(seed.line_id),
        "barcode": "460666AUDIT",
        "sticker_codes": sticker_codes,
        "order_sticker_barcodes": sticker_codes,
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
                        "pack_status": o.pack_status,
                        "sticker_code": o.sticker_code,
                        "sticker_barcode": o.sticker_barcode,
                        "supply_id": o.supply_id,
                        "seller_id": o.seller_id,
                    }
                    for o in orders
                ],
                "stock": str(await stock_snapshot()),
                "synthetic_provider_readbacks": synthetic_provider_readbacks,
            }
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=16692, access_log=False)

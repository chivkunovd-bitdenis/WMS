# ruff: noqa: E402
# conftest must configure the isolated database before importing product modules.
"""Local-only audit harness: real API/DB and exact loopback WB HTTP transport."""

from __future__ import annotations

import asyncio
import base64
import hashlib
from io import BytesIO
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import pytest
import qrcode
from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, func, select

assert os.environ.get("WMS_TEST_DATABASE_URL", "").endswith("/wms_test_666_browser_proof")
from conftest import _reset_database, create_app
from test_fbs_order_tape_concurrency import seed_tape, stock_snapshot
from test_fbs_kiz import _patch_wb_acceptance

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderMarking, FbsOrderProduct, FbsOrderReservation
from app.models.fbs_order import MARKING_KIND_SGTIN
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.marking_code import MarkingCode
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.services.fbs_print_asset_service import _persist_order_sticker_bytes
from app.services import fbs_marking_service, fbs_print_asset_service, fbs_shipment_pvz_service
from app.services import fbs_supply_transfer_service, fbs_kiz_service
from app.services import fbs_autopoll_service
from app.services import wildberries_client, wildberries_fbs_client
from app.services.wildberries_fbs_client import MarketplaceOrderMetaRow

patch = pytest.MonkeyPatch()
product_app = create_app()
client = httpx.AsyncClient(transport=httpx.ASGITransport(app=product_app), base_url="http://test")
seed = None
active_requests = 0
wb_sent_values: dict[int, str] = {}
wb_rejected_order_ids: set[int] = set()
synthetic_box_provider_events: list[dict[str, object]] = []
synthetic_transfer_events: list[dict[str, object]] = []
synthetic_transfer_orders: dict[str, set[int]] = {}
transfer_target_id: str | None = None


def _synthetic_qr_png(value: str) -> str:
    image = qrcode.make(value)
    payload = BytesIO()
    image.save(payload, format="PNG")
    return base64.b64encode(payload.getvalue()).decode("ascii")


async def synthetic_wb_box_stickers(
    _client,
    *,
    api_token: str,
    supply_id: str,
    trbx_ids: list[str],
    type: str = "png",
    marketplace_api_base: str | None = None,
) -> list[dict[str, str]]:
    del api_token, marketplace_api_base
    synthetic_box_provider_events.append({
        "operation": "GET_STICKER",
        "supply_id": supply_id,
        "type": type,
        "trbx_ids": list(trbx_ids),
        "decoded_values": list(trbx_ids),
    })
    return [
        {"trbxId": trbx_id, "file": _synthetic_qr_png(trbx_id), "barcode": f"SYNTHETIC-QR-{trbx_id}"}
        for trbx_id in trbx_ids
    ]


async def synthetic_wb_put(
    client,
    *,
    api_token: str,
    order_id: int,
    kind: str,
    value: str,
    marketplace_api_base: str | None = None,
) -> None:
    # Keep the application's real Wildberries serializer and HTTP client in
    # the path. The local receiver records the actual JSON body independently.
    await wildberries_client.put_marketplace_order_meta(
        client,
        api_token=api_token,
        order_id=order_id,
        kind=kind,
        value=value,
        marketplace_api_base=marketplace_api_base,
    )
    wb_sent_values[order_id] = value


async def synthetic_wb_meta_batch(
    client,
    *,
    api_token: str,
    order_ids: list[int],
    marketplace_api_base: str | None = None,
) -> list[MarketplaceOrderMetaRow]:
    return await wildberries_fbs_client.fetch_marketplace_orders_meta_batch(
        client,
        api_token=api_token,
        order_ids=order_ids,
        marketplace_api_base=marketplace_api_base,
    )


async def deny_external(*args, **kwargs):
    request = args[-1] if args else kwargs.get("request")
    url = getattr(request, "url", None)
    method = str(getattr(request, "method", "")).upper()
    host = getattr(url, "host", None)
    port = getattr(url, "port", None)
    path = getattr(url, "path", None)
    if (
        request is not None
        and host == "127.0.0.1"
        and port == 16710
        and (
            (method == "POST" and path in {
                "/api/v3/orders/stickers",
                "/api/marketplace/v3/orders/meta",
                "/configure-rejection",
            })
            or (method == "GET" and path == "/state")
            or (method == "PUT" and re.fullmatch(r"/api/v3/orders/\d+/meta/sgtin", path or ""))
            or (
                method == "DELETE"
                and re.fullmatch(r"/api/v3/orders/\d+/meta", path or "")
                and getattr(url, "query", b"").decode() == "key=sgtin"
            )
        )
    ):
        return await _ORIGINAL_HTTP_TRANSPORT(*args, **kwargs)
    raise RuntimeError("Audit forbids external HTTP except exact local WB sticker/meta endpoints")


_ORIGINAL_HTTP_TRANSPORT = httpx.AsyncHTTPTransport.handle_async_request
patch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", deny_external)
settings.wildberries_marketplace_api_base = "http://127.0.0.1:16710"
settings.e2e_mock_wb_marketplace_marking = False


async def synthetic_marketplace_token(_session, _tenant_id, _seller_id, _supply=None):
    # This value is only sent to the local loopback emulator and never logged.
    return "wms666-local-emulator-token"


async def synthetic_add_orders_to_marketplace_supply(
    _client, *, api_token: str, supply_id: str, order_ids: list[int]
) -> None:
    del api_token
    synthetic_transfer_events.append({"operation": "add_orders", "supply_id": supply_id, "order_ids": list(order_ids)})
    synthetic_transfer_orders.setdefault(supply_id, set()).update(order_ids)


async def synthetic_fetch_marketplace_supply_order_ids(
    _client, *, api_token: str, supply_id: str
) -> list[int]:
    del api_token
    synthetic_transfer_events.append({"operation": "read_orders", "supply_id": supply_id})
    return sorted(synthetic_transfer_orders.get(supply_id, set()))


import app.services.fbs_print_asset_service as print_asset_service  # noqa: E402

patch.setattr(print_asset_service, "_require_marketplace_token", synthetic_marketplace_token)
patch.setattr(fbs_shipment_pvz_service, "_require_marketplace_token", synthetic_marketplace_token)
patch.setattr(fbs_supply_transfer_service, "_require_marketplace_token", synthetic_marketplace_token)
patch.setattr(fbs_supply_transfer_service, "add_orders_to_marketplace_supply", synthetic_add_orders_to_marketplace_supply)
patch.setattr(fbs_supply_transfer_service, "fetch_marketplace_supply_order_ids", synthetic_fetch_marketplace_supply_order_ids)
# The packing-box service imports the cargo-place module through its own alias;
# patch that exact call boundary too, so box creation uses only the local fake token.
from app.services import fbs_packing_box_service  # noqa: E402

patch.setattr(fbs_packing_box_service.pvz_svc, "_require_marketplace_token", synthetic_marketplace_token)


@asynccontextmanager
async def lifespan(_app):
    yield
    await client.aclose()
    patch.undo()


app = FastAPI(lifespan=lifespan)


@app.post("/seed")
async def reset(request: Request):
    global seed, transfer_target_id
    options = await request.json()
    for _ in range(100):
        if active_requests == 0:
            break
        await asyncio.sleep(0.1)
    assert active_requests == 0, "Previous audit case still has active API requests"
    await _reset_database()
    seed = await seed_tape(client, patch, options.get("codes", 4))
    # `seed_tape` is shared with a concurrency test and replaces this client
    # boundary with AsyncMock. Restore the production client for this audit so
    # replacement/unlink sends are journaled by the loopback WB receiver.
    patch.setattr(
        fbs_kiz_service,
        "delete_marketplace_order_meta",
        wildberries_fbs_client.delete_marketplace_order_meta,
    )
    wb_sent_values.clear()
    wb_rejected_order_ids.clear()
    synthetic_box_provider_events.clear()
    synthetic_transfer_events.clear()
    synthetic_transfer_orders.clear()
    transfer_target_id = None
    # Keep the existing request-recording WB sticker emulator active for
    # order stickers. The route-level box-create scope below temporarily turns
    # on the application's cargo-place test double only while that call runs.
    settings.e2e_mock_wb_marketplace_supplies = False
    patch.setattr(fbs_marking_service, "put_marketplace_order_meta", synthetic_wb_put)
    patch.setattr(fbs_marking_service, "fetch_marketplace_orders_meta_batch", synthetic_wb_meta_batch)
    patch.setattr(fbs_print_asset_service, "fetch_marketplace_trbx_stickers", synthetic_wb_box_stickers)
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
            # A bare-flow proof must exercise the actual sticker request and
            # persistence path. Do not seed a sticker on the order before the
            # React workspace has a chance to request one from the WB emulator.
            order.sticker_code = None if options.get("bare") else f"AUDIT-STICKER-{index}"
            order.sticker_barcode = None if options.get("bare") else f"*AUDIT{index}"
            if options.get("stickers") and not options.get("bare"):
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
        if options.get("transfer_target"):
            source = await session.get(FbsSupply, seed.supply_id)
            assert source is not None
            target = FbsSupply(
                tenant_id=seed.tenant_id,
                seller_id=source.seller_id,
                warehouse_id=source.warehouse_id,
                name="Audit transfer target",
                status="assembling",
                delivery_type=source.delivery_type,
                wb_supply_id="WB-AUDIT-TRANSFER-TARGET",
                marketplace="wb",
                source="wms",
            )
            session.add(target)
            await session.flush()
            transfer_target_id = str(target.id)
            synthetic_transfer_orders[target.wb_supply_id] = set()
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
        "transfer_target_id": transfer_target_id,
        "headers": seed.headers,
    }


@app.post("/configure-wb-rejection")
async def configure_wb_rejection(request: Request):
    """Set the local WB test double's outcome after manual labels are printed."""
    payload = await request.json()
    order_id = uuid.UUID(str(payload["order_id"]))
    assert seed is not None and order_id in seed.order_ids
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        wb_order_id = order.wb_order_id
    rejected_value = str(payload["cis_code"])
    async with httpx.AsyncClient() as emulator_client:
        response = await emulator_client.post(
            "http://127.0.0.1:16710/configure-rejection",
            json={"orderId": wb_order_id, "rejectedValue": rejected_value},
        )
        response.raise_for_status()
    wb_rejected_order_ids.add(wb_order_id)
    return {
        "configured": True,
        "order_id": str(order_id),
        "wb_order_id": wb_order_id,
        "outcome": "rejected",
        "cis_sha256": hashlib.sha256(rejected_value.encode()).hexdigest(),
    }


@app.get("/provider-state")
async def provider_state():
    async with httpx.AsyncClient() as emulator_client:
        response = await emulator_client.get("http://127.0.0.1:16710/state")
        response.raise_for_status()
        receiver_state = response.json()
    return {
        "wb_sgtin_service_callback_values": dict(wb_sent_values),
        "wb_sgtin_service_callback_rejected_order_ids": sorted(wb_rejected_order_ids),
        "wb_http_receiver": receiver_state,
        "box_events": list(synthetic_box_provider_events),
        "transfer_events": list(synthetic_transfer_events),
        "transfer_orders": {key: sorted(values) for key, values in synthetic_transfer_orders.items()},
    }


@app.post("/run-pending-kiz-poll")
async def run_pending_kiz_poll(request: Request):
    """Advance the real seller autopoll once for this synthetic test fixture.

    The audit app does not run Celery's periodic scheduler. This local-only
    trigger invokes the same service function with the loopback WB transport so
    pending writes can reach an independently journaled provider response.
    """
    payload = await request.json()
    supply_id = uuid.UUID(str(payload["supply_id"]))
    assert seed is not None and supply_id == seed.supply_id
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        target = fbs_autopoll_service.SellerPollTarget(
            tenant_id=supply.tenant_id,
            seller_id=supply.seller_id,
        )
        async with httpx.AsyncClient() as http_client:
            result = await fbs_autopoll_service.sync_marking_verdicts_for_seller(
                session, target, http_client,
            )
            # Match the production Celery caller: it commits once after the
            # seller-level service returns, including resend_pending updates.
            await session.commit()
    return {
        "orders_checked": result.orders_checked,
        "orders_updated": result.orders_updated,
        "local_state": await snapshot(),
        "provider_state": await provider_state(),
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
    box_create = request.method == "POST" and path.endswith("/boxes")
    previous_box_mock = settings.e2e_mock_wb_marketplace_supplies
    if box_create:
        settings.e2e_mock_wb_marketplace_supplies = True
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
        if box_create:
            settings.e2e_mock_wb_marketplace_supplies = previous_box_mock
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
                        "sticker_code": o.sticker_code,
                        "sticker_barcode": o.sticker_barcode,
                        "sticker_status": o.sticker_status,
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
                        "checksum": asset.checksum,
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

"""WMS-628: a product hint disambiguates a barcode; it never replaces it."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.document_event import DocumentEvent
from app.models.fbs_order import FbsOrder, FbsOrderProduct, FbsOrderProductPick
from app.models.fbs_order_pick import FbsOrderPick, FbsOrderPickEvent
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product_barcode import ProductBarcode
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.user import User
from app.services import fbs_picking_service as picking
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)


@dataclass
class Case:
    headers: dict[str, str]
    tenant: uuid.UUID
    seller: uuid.UUID
    location: uuid.UUID
    product: uuid.UUID
    other: uuid.UUID
    supply: uuid.UUID
    orders: list[uuid.UUID]


async def _case(client: AsyncClient, marketplace: str = "wb") -> Case:
    headers, suffix, tenant = await _register_ff_admin(client)
    seller, warehouse, location = await _create_seller_and_warehouse(client, headers, suffix)
    product = await _create_product(
        client, headers, seller, sku="ФА_МОД274а/001/42", barcode="4119560418722",
    )
    other = await _create_product(
        client, headers, seller, sku="OTHER", barcode="5594804821589",
    )
    supply, orders, _ = await _seed_pick_supply(
        client, headers, tenant, seller, warehouse, location, product,
        stock_qty=4, order_specs=[(1, timedelta(hours=1)), (2, timedelta(hours=2))],
        barcode="ORDER-CODE", marketplace=marketplace,
    )
    _, other_orders, _ = await _seed_pick_supply(
        client, headers, tenant, seller, warehouse, location, other,
        stock_qty=4, order_specs=[(3, timedelta(hours=3))], barcode="OTHER-ORDER",
        marketplace=marketplace,
    )
    async with SessionLocal() as session:
        other_order = await session.get(FbsOrder, other_orders[0])
        assert other_order is not None
        other_order.supply_id = supply
        session.add(ProductBarcode(
            tenant_id=tenant, seller_id=seller, product_id=product, barcode="ALIAS",
        ))
        if marketplace == "ozon":
            session.add(ProductMarketplaceLink(
                tenant_id=tenant, seller_id=seller, product_id=product,
                marketplace="ozon", external_sku="10001", external_barcodes=["OZN10001"],
            ))
        await session.commit()
    return Case(headers, tenant, seller, location, product, other, supply, orders)


async def _snapshot() -> dict[str, list[tuple[Any, ...]]]:
    """Read persisted business data, including unsuccessful scan receipts."""
    async with SessionLocal() as session:
        return {
            model.__tablename__: sorted(
                [tuple(row) for row in (await session.execute(select(model.__table__))).all()],
                key=str,
            )
            for model in (
                InventoryBalance, InventoryMovement, FbsOrder, FbsOrderProduct,
                FbsOrderPick, FbsOrderPickEvent, FbsOrderProductPick, DocumentEvent,
            )
        }


async def _scan(
    case: Case, path: str, barcode: str, *, key: str | None = None,
    hint: bool = True, product: uuid.UUID | None = None,
) -> None:
    async with SessionLocal() as session:
        actor = await session.scalar(select(User).where(User.tenant_id == case.tenant))
        assert actor is not None
        kwargs: dict[str, Any] = {"idempotency_key": key or str(uuid.uuid4()), "actor": actor}
        if path == "pick_scan":
            call = picking.pick_scan(
                session, case.tenant, case.supply, barcode=barcode,
                product_id_hint=(product or case.product) if hint else None,
                storage_location_id=case.location, **kwargs,
            )
        else:
            call = picking.scan_pick_product(
                session, case.tenant, case.supply, product_barcode=barcode,
                product_id=(product or case.product) if hint else None,
                location_id=case.location, **kwargs,
            )
        try:
            await call
        except picking.FbsPickingError:
            # Commit on purpose: rejection must precede all business writes.
            await session.commit()
            raise
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["pick_scan", "scan_pick_product"])
@pytest.mark.parametrize("barcode", ["5594804821589", "UNKNOWN", "722", "   "])
async def test_wrong_barcode_with_hint_has_no_writes(
    async_client: AsyncClient, path: str, barcode: str,
) -> None:
    case = await _case(async_client)
    before = await _snapshot()
    with pytest.raises(picking.FbsPickingError) as error:
        await _scan(case, path, barcode)
    assert error.value.code == ("barcode_empty" if not barcode.strip() else "wrong_product")
    assert await _snapshot() == before
    await _scan(case, path, "4119560418722")


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["pick_scan", "scan_pick_product"])
@pytest.mark.parametrize("barcode", ["4119560418722", "ALIAS", "ФА_МОД274а/001/42", "ORDER-CODE"])
@pytest.mark.parametrize("hint", [True, False])
async def test_valid_codes_and_replay(
    async_client: AsyncClient, path: str, barcode: str, hint: bool,
) -> None:
    case = await _case(async_client)
    key = str(uuid.uuid4())
    await _scan(case, path, barcode, key=key, hint=hint)
    after = await _snapshot()
    await _scan(case, path, barcode, key=key, hint=hint)
    assert await _snapshot() == after
    await _scan(case, path, barcode, hint=hint)
    async with SessionLocal() as session:
        picks = (await session.scalars(select(FbsOrderPick))).all()
        assert len(picks) == 2
        assert {pick.product_id for pick in picks} == {case.product}
        quantity = await session.scalar(select(InventoryBalance.quantity).where(
            InventoryBalance.product_id == case.product,
            InventoryBalance.storage_location_id == case.location,
        ))
        assert quantity == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["pick_scan", "scan_pick_product"])
async def test_hint_preserves_selected_product_with_shared_order_code(
    async_client: AsyncClient, path: str,
) -> None:
    case = await _case(async_client)
    async with SessionLocal() as session:
        other = await session.scalar(select(FbsOrder).where(FbsOrder.product_id == case.other))
        assert other is not None
        other.wb_barcode = "ORDER-CODE"
        await session.commit()
    await _scan(case, path, "ORDER-CODE", product=case.other)
    async with SessionLocal() as session:
        pick = await session.scalar(select(FbsOrderPick))
        assert pick is not None and pick.product_id == case.other


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["pick_scan", "scan_pick_product"])
async def test_ozon_marketplace_code_and_wrong_hint(async_client: AsyncClient, path: str) -> None:
    case = await _case(async_client, marketplace="ozon")
    before = await _snapshot()
    with pytest.raises(picking.FbsPickingError) as error:
        await _scan(case, path, "OZN10001", product=case.other)
    assert error.value.code == "wrong_product"
    assert await _snapshot() == before
    await _scan(case, path, "OZN10001")
    async with SessionLocal() as session:
        pick = await session.scalar(select(FbsOrderProductPick))
        assert pick is not None and pick.product_id == case.product


@pytest.mark.asyncio
async def test_manual_pick_and_public_empty_scan(async_client: AsyncClient) -> None:
    case = await _case(async_client)
    before = await _snapshot()
    for path in ("scan", "scan-product"):
        response = await async_client.post(
            f"/operations/fbs-supplies/{case.supply}/pick/{path}",
            headers={**case.headers, "Idempotency-Key": str(uuid.uuid4())},
            json={
                "barcode": "   ", "product_barcode": "   ",
                "product_id": str(case.product), "location_id": str(case.location),
                "storage_location_id": str(case.location), "idempotency_key": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 422, response.text
    assert await _snapshot() == before
    response = await async_client.post(
        f"/operations/fbs-supplies/{case.supply}/pick/manual", headers=case.headers,
        json={"location_id": str(case.location), "product_id": str(case.product),
              "order_id": str(case.orders[0]), "idempotency_key": str(uuid.uuid4())},
    )
    assert response.status_code == 200, response.text
    async with SessionLocal() as session:
        pick = await session.scalar(select(FbsOrderPick))
        assert pick is not None and pick.product_id == case.product
        assert pick.scanned_product_barcode == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["pick_scan", "scan_pick_product"])
@pytest.mark.parametrize("scope", ["tenant", "seller", "supply"])
@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
async def test_hint_cannot_cross_product_scope(
    async_client: AsyncClient, path: str, scope: str, marketplace: str,
) -> None:
    case = await _case(async_client, marketplace=marketplace)
    if scope == "tenant":
        foreign = await _case(async_client)
        product_id = foreign.product
    else:
        seller = case.seller
        if scope == "seller":
            response = await async_client.post(
                "/sellers", headers=case.headers, json={"name": "Other seller"},
            )
            assert response.status_code in (200, 201), response.text
            seller = uuid.UUID(response.json()["id"])
        product_id = await _create_product(
            async_client, case.headers, seller, sku="OUTSIDE", barcode="OUTSIDE-CODE",
        )
    before = await _snapshot()
    with pytest.raises(picking.FbsPickingError) as error:
        await _scan(
            case, path, "4119560418722" if scope == "tenant" else "OUTSIDE-CODE",
            product=product_id,
        )
    assert error.value.code == "wrong_product"
    assert await _snapshot() == before


@pytest.mark.asyncio
async def test_public_hint_rejects_wrong_code_and_allows_retry(async_client: AsyncClient) -> None:
    case = await _case(async_client)
    before = await _snapshot()
    key = str(uuid.uuid4())
    body = {
        "barcode": "5594804821589", "product_id": str(case.product),
        "storage_location_id": str(case.location),
    }
    response = await async_client.post(
        f"/operations/fbs-supplies/{case.supply}/pick/scan",
        headers={**case.headers, "Idempotency-Key": key}, json=body,
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "wrong_product"
    assert await _snapshot() == before
    body["barcode"] = "4119560418722"
    response = await async_client.post(
        f"/operations/fbs-supplies/{case.supply}/pick/scan",
        headers={**case.headers, "Idempotency-Key": key}, json=body,
    )
    assert response.status_code == 200, response.text
    after = await _snapshot()
    # A committed request retried after losing its response returns the receipt.
    response = await async_client.post(
        f"/operations/fbs-supplies/{case.supply}/pick/scan",
        headers={**case.headers, "Idempotency-Key": key}, json=body,
    )
    assert response.status_code == 200, response.text
    assert await _snapshot() == after


@pytest.mark.asyncio
@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
@pytest.mark.parametrize("wrong_payload", ["barcode", "product"])
async def test_direct_scan_replay_rejects_changed_identity(
    async_client: AsyncClient, marketplace: str, wrong_payload: str,
) -> None:
    case = await _case(async_client, marketplace=marketplace)
    key = str(uuid.uuid4())
    await _scan(case, "scan_pick_product", "4119560418722", key=key)
    after = await _snapshot()
    with pytest.raises(picking.FbsPickingError) as error:
        await _scan(
            case, "scan_pick_product",
            "5594804821589" if wrong_payload == "barcode" else "4119560418722",
            product=case.other if wrong_payload == "product" else case.product, key=key,
        )
    assert error.value.code == "idempotency_key_reused"
    assert await _snapshot() == after
    await _scan(case, "scan_pick_product", "4119560418722", key=key)
    assert await _snapshot() == after


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["pick_scan", "scan_pick_product"])
async def test_hinted_sku_preserves_case_insensitive_frontend_contract(
    async_client: AsyncClient, path: str,
) -> None:
    case = await _case(async_client)
    await _scan(case, path, "фа_мод274А/001/42")


@pytest.mark.asyncio
@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
@pytest.mark.parametrize("path", ["pick_scan", "scan_pick_product"])
async def test_valid_replay_after_all_product_units_are_picked(
    async_client: AsyncClient, marketplace: str, path: str,
) -> None:
    case = await _case(async_client, marketplace=marketplace)
    key = str(uuid.uuid4())
    await _scan(case, path, "4119560418722", key=key)
    await _scan(case, path, "4119560418722")
    after = await _snapshot()
    await _scan(case, path, "4119560418722", key=key)
    assert await _snapshot() == after

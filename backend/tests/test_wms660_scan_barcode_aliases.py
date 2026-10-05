"""WMS-660: saved product barcodes resolve within the current WB supply."""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.document_event import DocumentEvent
from app.models.fbs_order import FbsOrder
from app.models.product import Product
from app.models.product_barcode import ProductBarcode
from tests.test_wms514_scan_auto_print import _seed_wb_supply

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize(
    "primary,alias",
    [("04640556102658", "4610264735875"), ("04640556141886", "4610264735912")],
)
@pytest.mark.parametrize("code_source", ["primary", "order", "alias"])
async def test_saved_codes_select_and_replay_without_consuming_next_order(
    async_client: AsyncClient, primary: str, alias: str, code_source: str,
) -> None:
    headers, supply_id, _ = await _seed_wb_supply(async_client)
    async with SessionLocal() as session:
        orders = list((await session.scalars(select(FbsOrder))).all())
        product = await session.get(Product, orders[0].product_id)
        assert product is not None
        product.wb_barcode = primary
        for order in orders:
            order.wb_barcode = "ORDER-CODE"
        session.add(ProductBarcode(
            tenant_id=product.tenant_id, seller_id=product.seller_id,
            product_id=product.id, barcode=alias,
        ))
        await session.commit()

    barcode = {"primary": primary, "order": "ORDER-CODE", "alias": alias}[code_source]
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    body = {
        "barcode": barcode, "idempotency_key": "scan-1", "print_chz": True,
        "print_qr": False,
    }
    first = await async_client.post(url, headers=headers, json=body)
    assert first.status_code == 200, first.text
    replay = await async_client.post(url, headers=headers, json=body)
    assert replay.status_code == 200, replay.text
    assert replay.json()["order_id"] == first.json()["order_id"]
    assert replay.json()["scan_id"] == first.json()["scan_id"]
    assert replay.json()["replayed"] is True

    # A different saved code for the same product shares the same unit reservations.
    second = await async_client.post(
        url, headers=headers, json={**body, "barcode": primary, "idempotency_key": "scan-2"},
    )
    assert second.status_code == 200, second.text
    assert second.json()["order_id"] != first.json()["order_id"]
    exhausted = await async_client.post(
        url, headers=headers, json={**body, "idempotency_key": "scan-3"},
    )
    assert exhausted.status_code == 409
    assert exhausted.json()["detail"]["code"] == "scan_product_exhausted"
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(DocumentEvent)) == 2


@pytest.mark.parametrize("scope", ["supply", "seller", "tenant"])
async def test_alias_outside_current_scope_is_not_selected(
    async_client: AsyncClient, scope: str,
) -> None:
    headers, supply_id, _ = await _seed_wb_supply(async_client, order_count=1)
    async with SessionLocal() as session:
        order = await session.scalar(select(FbsOrder))
        assert order is not None
        tenant_id, seller_id = order.tenant_id, order.seller_id
    if scope == "tenant":
        _, other_supply, _ = await _seed_wb_supply(async_client, order_count=1)
        async with SessionLocal() as session:
            foreign_order = await session.scalar(select(FbsOrder).where(
                FbsOrder.supply_id == other_supply,
            ))
            assert foreign_order is not None
            tenant_id, seller_id = foreign_order.tenant_id, foreign_order.seller_id
    elif scope == "seller":
        response = await async_client.post(
            "/sellers", headers=headers, json={"name": "Other seller WMS-660"},
        )
        assert response.status_code in {200, 201}, response.text
        seller_id = uuid.UUID(response.json()["id"])
    async with SessionLocal() as session:
        other = Product(
            tenant_id=tenant_id, seller_id=seller_id, name="Outside supply",
            sku_code="OUTSIDE-660", wb_barcode="OUTSIDE-PRIMARY",
        )
        session.add(other)
        await session.flush()
        session.add(ProductBarcode(
            tenant_id=tenant_id, seller_id=seller_id, product_id=other.id,
            barcode="OUTSIDE-ALIAS",
        ))
        await session.commit()
    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/scan-auto-print", headers=headers,
        json={"barcode": "OUTSIDE-ALIAS", "idempotency_key": "outside",
              "print_chz": True, "print_qr": False},
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["code"] == "scan_product_not_found"
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(DocumentEvent)) == 0


async def test_alias_collision_with_another_product_is_ambiguous_but_row_scan_still_works(
    async_client: AsyncClient,
) -> None:
    headers, supply_id, _ = await _seed_wb_supply(async_client)
    async with SessionLocal() as session:
        orders = list((await session.scalars(select(FbsOrder).order_by(FbsOrder.wb_order_id))).all())
        first = orders[0]
        other = Product(
            tenant_id=first.tenant_id, seller_id=first.seller_id, name="Second product",
            sku_code="OTHER-660", wb_barcode="SHARED-660",
        )
        session.add(other)
        await session.flush()
        orders[1].product_id = other.id
        orders[1].wb_barcode = "OTHER-ORDER"
        session.add(ProductBarcode(
            tenant_id=first.tenant_id, seller_id=first.seller_id,
            product_id=first.product_id, barcode="SHARED-660",
        ))
        first_id = first.id
        await session.commit()
    url = f"/operations/fbs-supplies/{supply_id}/scan-auto-print"
    body = {"barcode": "SHARED-660", "idempotency_key": "ambiguous",
            "print_chz": True, "print_qr": False}
    response = await async_client.post(url, headers=headers, json=body)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "scan_product_ambiguous"
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(DocumentEvent)) == 0
    explicit = await async_client.post(
        url, headers=headers,
        json={**body, "barcode": f"order:{first_id}", "order_id": str(first_id)},
    )
    assert explicit.status_code == 200, explicit.text
    assert explicit.json()["order_id"] == str(first_id)

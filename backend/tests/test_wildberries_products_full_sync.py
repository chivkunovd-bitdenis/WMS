"""WMS-276/277: complete Products import and ordinary FBS remapping."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrderReservation
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services import wildberries_product_sync_service as products_sync
from app.services import wildberries_sync_service as cards_sync
from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row


@pytest.mark.asyncio
async def test_products_import_all_pages_then_existing_order_maps_and_reserves_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = db_session
    tenant = Tenant(name="WMS277", slug="wms277")
    session.add(tenant)
    await session.flush()
    seller = Seller(tenant_id=tenant.id, name="WMS277 seller")
    warehouse = Warehouse(tenant_id=tenant.id, name="Warehouse", code="277")
    session.add_all([seller, warehouse])
    await session.flush()
    location = StorageLocation(tenant_id=tenant.id, warehouse_id=warehouse.id, code="A", barcode="A")
    session.add(location)
    await session.commit()
    row = {
        "id": 277205, "nmId": 205, "chrtId": 205, "skus": ["BAR-205"],
        "createdAt": datetime.now(UTC).isoformat(),
    }
    order, created = await upsert_order_from_wb_row(session, tenant.id, seller.id, row)
    assert created and order.product_id is None
    order.warehouse_id = warehouse.id
    await session.commit()
    cursors = []

    def upstream(request: httpx.Request) -> httpx.Response:
        cursor = json.loads(request.content)["settings"]["cursor"]
        offset = cursor.get("nmID", 0)
        cursors.append(offset)
        end = min(offset + 100, 205)
        cards = [
            {"nmID": i, "vendorCode": f"WMS277-{i}", "title": f"Product {i}",
             "sizes": [{"chrtID": i, "techSize": "0", "skus": [f"BAR-{i}"]}]}
            for i in range(offset + 1, end + 1)
        ]
        return httpx.Response(200, json={"cards": cards, "cursor": {
            "updatedAt": "2026-09-08T00:00:00Z", "nmID": end, "total": len(cards),
        }})

    monkeypatch.setattr(products_sync, "get_decrypted_tokens_for_seller",
                        AsyncMock(return_value=("synthetic-token", None)))
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        result = await products_sync.sync_wb_products_for_seller(
            session, tenant.id, seller.id, client,
        )
    assert cursors == [0, 100, 200]
    assert result["cards_received"] == result["products_created"] == 205
    assert await session.scalar(select(func.count(Product.id))) == 205
    assert await session.scalar(select(func.count(InventoryBalance.id))) == 0
    assert await session.scalar(select(func.count(InventoryMovement.id))) == 0
    assert order.product_id is None  # Catalog import does not replay order history.

    mapped, created = await upsert_order_from_wb_row(
        session, tenant.id, seller.id, row, preserve_unmapped_warehouse=True,
    )
    await session.commit()
    product = await session.get(Product, mapped.product_id)
    assert not created and product is not None and product.wb_nm_id == 205
    assert mapped.mapping_status == "mapped"
    assert await session.scalar(select(func.count(FbsOrderReservation.id))) == 0

    # Actual stock and the existing operator rule are necessary for reservation.
    product.fbs_percent = 100
    product.fbs_stock_sync_enabled = True
    balance = InventoryBalance(
        tenant_id=tenant.id, product_id=product.id, storage_location_id=location.id,
        quantity=1, quantity_unpacked=1, quantity_packed=0,
    )
    session.add(balance)
    await session.commit()
    for _ in range(2):
        await upsert_order_from_wb_row(
            session, tenant.id, seller.id, row, preserve_unmapped_warehouse=True,
        )
        await session.commit()
    assert mapped.reserve_status == "reserved"
    assert await session.scalar(select(func.sum(FbsOrderReservation.quantity))) == 1
    await session.refresh(balance)
    assert balance.quantity == balance.quantity_unpacked == 1
    assert balance.quantity_packed == 0
    assert await session.scalar(select(func.count(InventoryMovement.id))) == 0


@pytest.mark.asyncio
async def test_products_sync_rejects_partial_page_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(products_sync, "get_decrypted_tokens_for_seller",
                        AsyncMock(return_value=("synthetic-token", None)))
    saved = AsyncMock()
    monkeypatch.setattr(products_sync, "upsert_imported_cards", saved)
    monkeypatch.setattr(products_sync, "upsert_products_from_wb_cards", saved)
    fetch = AsyncMock(side_effect=[
        {"cards": [{"nmID": i} for i in range(100)],
         "cursor": {"total": 100, "updatedAt": "stamp", "nmID": 100}},
        {"cards": [{"nmID": i} for i in range(100)],
         "cursor": {"total": 100, "updatedAt": "stamp", "nmID": 100}},
    ])
    monkeypatch.setattr(cards_sync, "fetch_cards_list", fetch)
    async with httpx.AsyncClient() as client:
        with pytest.raises(cards_sync.WildberriesSyncError, match="wb_pagination_stalled"):
            await products_sync.sync_wb_products_for_seller(
                AsyncMock(), uuid.uuid4(), uuid.uuid4(), client,
            )
    saved.assert_not_awaited()

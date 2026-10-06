"""WMS-673 C10: actual API/services preserve business state and access boundaries.

Uses tests' isolated SQLite DB, never shared WMS-517 PostgreSQL. External HTTP
is forbidden; only the in-process ASGI client is permitted.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.api.fbs_orders import FbsWorklistOrderOut
from app.db.session import SessionLocal
from app.models import Base
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.product import Product
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.models.user import User
from app.services.fbs_stock_publish_service import drain_background_stock_publish_tasks
from app.services.fbs_stock_sync_service import drain_zero_publish_background_tasks
from app.services.fbs_worklist_service import _map_order
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)


async def _business_snapshot():
    prefixes = ("fbs_", "inventory_", "outbound_", "warehouse_", "storage_", "product")
    async with SessionLocal() as session:
        return {
            table.name: sorted(
                [
                    tuple(repr(value) for value in row)
                    for row in (await session.execute(select(table))).all()
                ]
            )
            for table in Base.metadata.sorted_tables
            if table.name.startswith(prefixes)
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
async def test_c10_real_print_reads_preserve_business_state_and_tenant_role_access(
    async_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    marketplace: str,
):
    original_send = httpx.AsyncClient.send

    async def local_only(self, request, *args, **kwargs):
        assert request.url.host == "test", "Printing must not call a marketplace"
        return await original_send(self, request, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", local_only)
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    foreign_headers, _, _ = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client,
        headers,
        suffix,
    )
    barcode = f"673{suffix[-10:]}"
    product_id = await _create_product(
        async_client,
        headers,
        seller_id,
        sku=f"WMS673-{suffix}",
        barcode=barcode,
    )
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        product.wb_nm_id = 673
        session.add(
            SellerWildberriesImportedCard(
                tenant_id=tenant_id,
                seller_id=seller_id,
                nm_id=673,
                raw_json={"characteristics": [{"name": "Цвет", "value": "Бордовый WMS673"}]},
            )
        )
        await session.commit()
    supply_id, _, _ = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=9,
        order_specs=[(673, timedelta(hours=24))],
        barcode=barcode,
        marketplace=marketplace,
        position_quantity=2,
    )
    await drain_background_stock_publish_tasks()
    await drain_zero_publish_background_tasks()
    async with SessionLocal() as session:
        order = await session.scalar(select(FbsOrder).where(FbsOrder.supply_id == supply_id))
        assert order is not None
        order.wb_nm_id = 673
        await session.commit()
    base = f"/operations/fbs-supplies/{supply_id}"
    before = await _business_snapshot()
    for _ in range(2):
        response = await async_client.get(f"{base}/workspace", headers=headers)
        assert response.status_code == 200, response.text
        order = response.json()["orders"][0]
        assert order["product"]["color"] == "Бордовый WMS673"
        if marketplace == "ozon":
            assert order["positions"][0]["color"] == "Бордовый WMS673"
        options = await async_client.get(f"{base}/pick-options", headers=headers)
        assert options.status_code == 200, options.text
    assert await _business_snapshot() == before
    for endpoint in ("workspace", "pick-options"):
        foreign = await async_client.get(f"{base}/{endpoint}", headers=foreign_headers)
        assert foreign.status_code == 404, foreign.text
        assert "Бордовый WMS673" not in foreign.text
        anonymous = await async_client.get(f"{base}/{endpoint}")
        assert anonymous.status_code == 401, anonymous.text
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.tenant_id == tenant_id))
        assert user is not None
        user.role = "seller"
        user.seller_id = seller_id
        await session.commit()
    for endpoint in ("workspace", "pick-options"):
        denied = await async_client.get(f"{base}/{endpoint}", headers=headers)
        assert denied.status_code == 403, denied.text
        assert "Бордовый WMS673" not in denied.text
    assert await _business_snapshot() == before


def test_real_marketplace_mapping_supplies_exact_product_and_position_colors():
    """Generate frontend default fixtures through production mapping + API schema.

    Edge values in frontend tests remain deliberate null/HTML/grouping inputs.
    Normal WB/Ozon colors/identities are this actual marketplace projection.
    """
    now = datetime(2026, 10, 6, 12, tzinfo=UTC)
    seller = uuid4()
    products = [
        Product(
            id=uuid4(),
            seller_id=seller,
            name=f"Товар {key}",
            wb_nm_id=1673 + i,
            wb_barcode=f"WB-CODE-{key}",
            wb_size="46",
            wb_vendor_code=f"ART-{key}",
        )
        for i, key in enumerate(["red", "blue"])
    ]
    cards = {
        (seller, product.wb_nm_id): SellerWildberriesImportedCard(
            seller_id=seller,
            nm_id=product.wb_nm_id,
            raw_json={"characteristics": [{"name": "Цвет", "value": [color]}]},
        )
        for product, color in zip(products, ["Красный", "Синий"], strict=True)
    }
    ctx = {
        key: {}
        for key in (
            "sellers",
            "warehouses",
            "wb_names",
            "ozon_photos",
            "availability",
            "locations",
            "markings",
            "picks",
            "sticker_assets",
        )
    }
    ctx.update(
        products={p.id: p for p in products},
        cards=cards,
        address_storage_enabled=False,
        marketplace_bindings={
            p.id: [{"marketplace": "ozon", "external_barcodes": [barcode]}]
            for p, barcode in zip(products, ["OZ-RED", "OZ-BLUE"], strict=True)
        },
    )

    def order(product, marketplace, index):
        return FbsOrder(
            id=uuid4(),
            seller_id=seller,
            product_id=product.id,
            marketplace=marketplace,
            wb_order_id=673000 + index,
            wb_nm_id=product.wb_nm_id,
            external_order_id="OZ-673-POSTING" if marketplace == "ozon" else None,
            status="new",
            supplier_status="new",
            mapping_status="mapped",
            sticker_status="not_requested",
            pick_status="pending",
            pack_status="pending",
            created_at_wb=now,
            deadline_at=now + timedelta(days=1),
            product_positions=[],
        )

    wb = [order(p, "wb", i) for i, p in enumerate(products)]
    oz = order(products[0], "ozon", 0)
    positions = [
        FbsOrderProduct(
            id=uuid4(),
            product_id=p.id,
            name=f"{label} позиция Ozon",
            offer_id=f"OZ-ART-{key}",
            ozon_sku=673101 + i,
            quantity=qty,
            reserved_quantity=qty,
            picked_quantity=picked,
        )
        for i, (p, label, key, qty, picked) in enumerate(
            zip(products, ["Первая", "Вторая"], ["RED", "BLUE"], [3, 2], [1, 2], strict=True)
        )
    ]
    oz.product_positions = positions
    ctx["positions"] = {oz.id: positions}

    def project(item):
        return FbsWorklistOrderOut(**_map_order(item, ctx, now)).model_dump(mode="json")

    payload = {"wb": [project(item)["product"] for item in wb], "ozon": project(oz)}
    assert [p["color"] for p in payload["wb"]] == ["Красный", "Синий"]
    assert [
        (p["color"], p["barcode"], p["sku"], p["quantity"]) for p in payload["ozon"]["positions"]
    ] == [("Красный", "OZ-RED", "673101", 3), ("Синий", "OZ-BLUE", "673102", 2)]
    assert payload["ozon"]["product"]["color"] == "Красный"
    assert payload["ozon"]["product"]["wb_article"] is None
    if target := os.environ.get("WMS673_MAPPING_FIXTURE"):
        Path(target).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

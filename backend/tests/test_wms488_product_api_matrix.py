"""WMS-488: real API requests and DB snapshots across seller/tenant boundaries."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from test_wms488_catalog_isolation import _headers, _seed

from app.db.session import SessionLocal
from app.models.fbs_print_asset import FbsPrintAsset
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.stock_direction import StockDirection
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse

RULE = {"same_everywhere": True, "percent": 40, "publish": False, "publish_ozon": False}
PERIOD = {"date_from": "2026-09-01T00:00:00Z", "date_to": "2026-09-30T00:00:00Z"}


async def _catalog():
    users, products, warehouse = await _seed()
    directions = {}
    async with SessionLocal() as session:
        for key, product in products.items():
            product = await session.get(Product, product.id)
            assert product is not None
            product.packaging_instructions = f"Private instructions {key}"
            product.fbs_stock_limit = 9
            product.fbs_percent = 50
            target_warehouse = warehouse
            if key == "foreign":
                target_warehouse = Warehouse(
                    tenant_id=product.tenant_id,
                    code="FOREIGN",
                    name="Foreign warehouse",
                )
                session.add(target_warehouse)
                await session.flush()
            location = StorageLocation(
                tenant_id=product.tenant_id,
                warehouse_id=target_warehouse.id,
                code=f"CELL-{key}",
                barcode=f"CELL-BARCODE-{key}",
            )
            session.add(location)
            await session.flush()
            session.add_all(
                [
                    InventoryBalance(
                        tenant_id=product.tenant_id,
                        product_id=product.id,
                        storage_location_id=location.id,
                        quantity=20,
                    ),
                    InventoryMovement(
                        tenant_id=product.tenant_id,
                        product_id=product.id,
                        seller_id=product.seller_id,
                        warehouse_id=target_warehouse.id,
                        storage_location_id=location.id,
                        quantity_delta=20,
                        movement_type="inbound_intake",
                        created_at=datetime(2026, 9, 10, tzinfo=UTC),
                    ),
                    ProductDimensionEvent(
                        tenant_id=product.tenant_id,
                        product_id=product.id,
                        source="manual",
                        fingerprint=f"event-{key}",
                        container_basis=f"Private event {key}",
                    ),
                ]
            )
            direction = StockDirection(
                tenant_id=product.tenant_id,
                product_id=product.id,
                name=f"Private direction {key}",
                quantity=0,
            )
            session.add(direction)
            await session.flush()
            directions[key] = direction.id
        await session.commit()
    return users, products, directions


async def _snapshot(product_ids: list[uuid.UUID] | None = None):
    """Compare complete stored rows, including timestamps and dependent records."""
    result = {}
    async with SessionLocal() as session:
        for model in (
            Product,
            ProductDimensionEvent,
            StockDirection,
            ProductMarketplaceLink,
            InventoryBalance,
            InventoryMovement,
        ):
            table = model.__table__
            query = select(table).order_by(table.c.id)
            if product_ids is not None:
                column = table.c.id if model is Product else table.c.product_id
                query = query.where(column.in_(product_ids))
            result[table.name] = (await session.execute(query)).all()
    return result


DIRECT = [
    ("GET", "/products/{pid}/dimensions/history", None),
    ("PATCH", "/products/{pid}/dimensions", {"length_mm": 20, "width_mm": 30, "height_mm": 40}),
    ("PATCH", "/products/{pid}/packaging-instructions", {"packaging_instructions": "Tampered"}),
    ("GET", "/products/{pid}/stock-directions", None),
    ("POST", "/products/{pid}/stock-directions", {"name": "Tampered", "quantity": 0}),
    ("PATCH", "/products/stock-directions/{did}", {"name": "Tampered"}),
    ("DELETE", "/products/stock-directions/{did}", None),
    ("GET", "/products/{pid}/fbs-rule", None),
    ("PUT", "/products/{pid}/fbs-rule", RULE),
    ("PATCH", "/products/{pid}/fbs-stock-sync", {"fbs_stock_limit": 3}),
]


@pytest.mark.parametrize("target", ["b", "foreign"])
@pytest.mark.parametrize(("method", "path", "body"), DIRECT)
async def test_foreign_product_direct_requests_disclose_nothing_and_write_nothing(
    async_client: AsyncClient,
    target: str,
    method: str,
    path: str,
    body: dict | None,
) -> None:
    users, products, directions = await _catalog()
    before = await _snapshot()
    response = await async_client.request(
        method,
        path.format(pid=products[target].id, did=directions[target]),
        headers=_headers(users["a"]),
        json=body,
    )
    expected = 404 if target == "foreign" or path.endswith("/dimensions/history") else 403
    assert response.status_code == expected, response.text
    assert products[target].name not in response.text
    assert str(products[target].id) not in response.text
    assert await _snapshot() == before


@pytest.mark.parametrize("target", ["a", "b", "foreign"])
async def test_seller_cannot_use_ff_creation_import_merge_link_or_print_routes(
    async_client: AsyncClient,
    target: str,
) -> None:
    users, products, _ = await _catalog()
    before = await _snapshot()
    product = products[target]
    async with SessionLocal() as session:
        asset = FbsPrintAsset(
            tenant_id=product.tenant_id,
            seller_id=product.seller_id,
            kind="operator_document",
            status="ready",
            content_type="image/png",
        )
        session.add(asset)
        await session.commit()
        asset_before = (await session.execute(select(FbsPrintAsset.__table__))).all()
    requests = [
        (
            "POST",
            "/products",
            {"name": "Tampered", "sku_code": "NEW", "seller_id": str(product.seller_id)},
        ),
        ("POST", "/products/merge", {"product_ids": [str(products["a"].id), str(product.id)]}),
        ("PATCH", f"/products/{product.id}/ozon-link", {"ozon_sku": "TAMPERED"}),
        (
            "POST",
            f"/products/{product.id}/dimensions/container",
            {"volume_liters": 5, "container_basis": "X"},
        ),
        ("POST", f"/products/{product.id}/dimensions/restore-wb", None),
        ("GET", "/products/import-tz/template", None),
        ("GET", f"/operations/fbs-print-assets/{asset.id}/content", None),
    ]
    for method, path, body in requests:
        response = await async_client.request(method, path, headers=_headers(users["a"]), json=body)
        assert response.status_code == 403, (method, path, response.text)
    for action in ("preview", "apply"):
        response = await async_client.post(
            f"/products/import-tz/{action}",
            headers=_headers(users["a"]),
            data={"seller_id": str(product.seller_id)},
            files={
                "file": (
                    "products.xlsx",
                    b"irrelevant: access denied before reading file",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 403, response.text
    print_preview = await async_client.get(
        f"/operations/print/sorting/{uuid.uuid4()}/label",
        headers=_headers(users["a"]),
        params={"kind": "product", "object_id": str(product.id)},
    )
    assert print_preview.status_code == 403, print_preview.text
    assert await _snapshot() == before
    async with SessionLocal() as session:
        assert (await session.execute(select(FbsPrintAsset.__table__))).all() == asset_before


@pytest.mark.parametrize("target", ["b", "foreign"])
@pytest.mark.parametrize(
    "operation", ["rule-read", "rule-write", "reset", "sync", "balance", "honest-sign"]
)
async def test_mixed_bulk_requests_preserve_foreign_rows(
    async_client: AsyncClient,
    target: str,
    operation: str,
) -> None:
    users, products, _ = await _catalog()
    ids = [str(products["a"].id), str(products[target].id)]
    before_all = await _snapshot()
    before_foreign = await _snapshot([products["b"].id, products["foreign"].id])
    cases = {
        "rule-read": ("POST", "/products/fbs-rule/bulk", {"product_ids": ids}),
        "rule-write": ("PUT", "/products/fbs-rule", {"product_ids": ids, "rule": RULE}),
        "reset": ("POST", "/products/fbs-rule/reset-legacy-limits", {"product_ids": ids}),
        "sync": (
            "PATCH",
            "/products/fbs-stock-sync/bulk",
            {"product_ids": ids, "fbs_stock_sync_enabled": False, "fbs_stock_limit": 3},
        ),
        "balance": ("PATCH", "/products/fbs-stock-limit/from-balance/bulk", {"product_ids": ids}),
        "honest-sign": (
            "PATCH",
            "/products/requires-honest-sign/bulk",
            {"product_ids": ids, "requires_honest_sign": True},
        ),
    }
    method, path, body = cases[operation]
    response = await async_client.request(method, path, headers=_headers(users["a"]), json=body)
    if operation in {"rule-read", "rule-write", "reset"}:
        assert response.status_code == (403 if target == "b" else 404), response.text
        assert await _snapshot() == before_all
    else:
        assert response.status_code == 200, response.text
        assert response.json()["updated_count"] == 1
        # The existing from-balance contract echoes submitted IDs as not_found;
        # it must never reveal foreign names or return them as updated products.
        assert products[target].name not in response.text
        if operation == "balance":
            assert {row["product_id"] for row in response.json()["updated"]} == {ids[0]}
            assert response.json()["skipped"] == [{"product_id": ids[1], "reason": "not_found"}]
        assert await _snapshot([products["b"].id, products["foreign"].id]) == before_foreign


async def test_own_product_actions_remain_available(async_client: AsyncClient) -> None:
    users, products, _ = await _catalog()
    pid = products["a"].id
    headers = _headers(users["a"])
    foreign_before = await _snapshot([products["b"].id, products["foreign"].id])
    for method, path, body in (
        ("GET", f"/products/{pid}/dimensions/history", None),
        (
            "PATCH",
            f"/products/{pid}/dimensions",
            {"length_mm": 20, "width_mm": 30, "height_mm": 40},
        ),
        (
            "PATCH",
            f"/products/{pid}/packaging-instructions",
            {"packaging_instructions": "Own updated"},
        ),
        ("GET", f"/products/{pid}/stock-directions", None),
        ("GET", f"/products/{pid}/fbs-rule", None),
        ("PUT", f"/products/{pid}/fbs-rule", RULE),
        ("PATCH", f"/products/{pid}/fbs-stock-sync", {"fbs_stock_limit": 7}),
        ("POST", "/products/fbs-rule/bulk", {"product_ids": [str(pid)]}),
        ("PUT", "/products/fbs-rule", {"product_ids": [str(pid)], "rule": RULE}),
        ("POST", "/products/fbs-rule/reset-legacy-limits", {"product_ids": [str(pid)]}),
    ):
        response = await async_client.request(method, path, headers=headers, json=body)
        assert response.status_code == 200, (method, path, response.text)
    created = await async_client.post(
        f"/products/{pid}/stock-directions",
        headers=headers,
        json={"name": "Own", "quantity": 0},
    )
    assert created.status_code == 201, created.text
    did = created.json()["id"]
    changed = await async_client.patch(
        f"/products/stock-directions/{did}",
        headers=headers,
        json={"name": "Own edited"},
    )
    assert changed.status_code == 200 and changed.json()["name"] == "Own edited"
    removed = await async_client.delete(f"/products/stock-directions/{did}", headers=headers)
    assert removed.status_code == 204
    assert await _snapshot([products["b"].id, products["foreign"].id]) == foreign_before


@pytest.mark.parametrize("target", ["b", "foreign"])
@pytest.mark.parametrize("path", ["/reports/inventory", "/reports/inventory/export.csv"])
async def test_seller_export_and_report_ignore_foreign_seller_override(
    async_client: AsyncClient,
    target: str,
    path: str,
) -> None:
    users, products, _ = await _catalog()
    params = {**PERIOD, "seller_id": str(products[target].seller_id), "group_by": "product"}
    response = await async_client.get(path, headers=_headers(users["a"]), params=params)
    assert response.status_code == 200, response.text
    assert products["a"].sku_code in response.text
    for key in ("b", "foreign"):
        for value in (products[key].sku_code, products[key].name, str(products[key].id)):
            assert value not in response.text
    hidden = await async_client.get(
        path,
        headers=_headers(users["a"]),
        params={**params, "search": products[target].sku_code},
    )
    assert hidden.status_code == (422 if path.endswith(".csv") else 200), hidden.text
    if path.endswith(".csv"):
        assert hidden.json()["detail"] == "nothing to export for the selected period"
    else:
        assert hidden.json()["rows"] == []
        assert hidden.json()["total"] == 0

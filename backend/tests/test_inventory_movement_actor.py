from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import fulfill_inbound_via_box_scans, post_primary_accept
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.storage_location import StorageLocation


async def _register_admin(
    async_client: AsyncClient,
    *,
    label: str,
) -> tuple[dict[str, str], str]:
    unique = uuid.uuid4().hex
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Actor test {label}",
            "slug": f"actor-{label}-{unique}",
            "admin_email": f"actor-{label}-{unique}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {
        "Authorization": f"Bearer {registered.json()['access_token']}"
    }
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    return headers, me.json()["id"]


async def _create_inventory_context(
    async_client: AsyncClient,
    headers: dict[str, str],
) -> tuple[str, str, str, str, str]:
    unique = uuid.uuid4().hex
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Actor warehouse", "code": f"actor-{unique}"},
    )
    assert warehouse.status_code == 200, warehouse.text
    warehouse_id = warehouse.json()["id"]

    source = await async_client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=headers,
        json={"code": "ACTOR-SOURCE"},
    )
    assert source.status_code == 200, source.text
    destination = await async_client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=headers,
        json={"code": "ACTOR-DESTINATION"},
    )
    assert destination.status_code == 200, destination.text

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Actor product",
            "sku_code": f"ACTOR-{unique}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    assert product.status_code == 200, product.text
    return (
        warehouse_id,
        source.json()["id"],
        destination.json()["id"],
        product.json()["id"],
        product.json()["sku_code"],
    )


@pytest.mark.asyncio
async def test_inbound_post_records_authenticated_actor_and_returns_it_from_movement_api(
    async_client: AsyncClient,
) -> None:
    """Normal path: the user who posts inbound stock is the journal actor."""
    headers, actor_id = await _register_admin(async_client, label="inbound")
    warehouse_id, source_id, _, product_id, sku_code = await _create_inventory_context(
        async_client, headers
    )

    base = "/operations/inbound-intake-requests"
    created = await async_client.post(
        base,
        headers=headers,
        json={"warehouse_id": warehouse_id},
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]
    line = await async_client.post(
        f"{base}/{request_id}/lines",
        headers=headers,
        json={
            "product_id": product_id,
            "expected_qty": 3,
            "storage_location_id": source_id,
        },
    )
    assert line.status_code == 201, line.text
    await post_primary_accept(async_client, base, request_id, headers)
    await fulfill_inbound_via_box_scans(
        async_client,
        headers,
        request_id,
        sku_code,
        3,
    )
    verified = await async_client.post(
        f"{base}/{request_id}/verify", headers=headers
    )
    assert verified.status_code == 200, verified.text
    posted = await async_client.post(f"{base}/{request_id}/post", headers=headers)
    assert posted.status_code == 200, posted.text

    movements = await async_client.get(
        f"{base}/{request_id}/movements", headers=headers
    )
    assert movements.status_code == 200, movements.text
    rows = movements.json()
    assert rows
    assert {row["actor_user_id"] for row in rows} == {actor_id}


@pytest.mark.asyncio
async def test_transfer_uses_authenticated_actor_on_both_legs_and_ignores_spoofed_actor(
    async_client: AsyncClient,
) -> None:
    """Adversarial path: a client cannot attribute its transfer to another user."""
    headers, actor_id = await _register_admin(async_client, label="transfer")
    _, foreign_actor_id = await _register_admin(async_client, label="foreign")
    _, source_id, destination_id, product_id, _ = await _create_inventory_context(
        async_client, headers
    )

    async with SessionLocal() as session:
        source = await session.get(StorageLocation, uuid.UUID(source_id))
        product = await session.get(Product, uuid.UUID(product_id))
        assert source is not None
        assert product is not None
        session.add(
            InventoryBalance(
                tenant_id=product.tenant_id,
                storage_location_id=source.id,
                product_id=product.id,
                quantity=10,
                quantity_unpacked=10,
                quantity_packed=0,
            )
        )
        await session.commit()

    transferred = await async_client.post(
        "/operations/stock-transfers",
        headers=headers,
        json={
            "from_storage_location_id": source_id,
            "to_storage_location_id": destination_id,
            "product_id": product_id,
            "quantity": 4,
            "actor_user_id": foreign_actor_id,
        },
    )
    assert transferred.status_code == 200, transferred.text

    async with SessionLocal() as session:
        result = await session.execute(
            select(InventoryMovement)
            .where(
                InventoryMovement.product_id == uuid.UUID(product_id),
                InventoryMovement.movement_type.in_(
                    ("stock_transfer_out", "stock_transfer_in")
                ),
            )
            .order_by(InventoryMovement.quantity_delta)
        )
        transfer_legs = list(result.scalars())
    assert len(transfer_legs) == 2
    assert transfer_legs[0].transfer_group_id == transfer_legs[1].transfer_group_id
    assert {str(row.actor_user_id) for row in transfer_legs} == {actor_id}
    assert foreign_actor_id not in {str(row.actor_user_id) for row in transfer_legs}

    listed = await async_client.get(
        "/operations/inventory-movements",
        headers=headers,
        params={"limit": 20},
    )
    assert listed.status_code == 200, listed.text
    api_legs = [
        row
        for row in listed.json()
        if row["movement_type"] in {"stock_transfer_out", "stock_transfer_in"}
    ]
    assert len(api_legs) == 2
    assert {row["actor_user_id"] for row in api_legs} == {actor_id}


@pytest.mark.asyncio
async def test_inventory_movement_api_returns_null_actor_for_historical_row(
    async_client: AsyncClient,
) -> None:
    """Legacy/system rows have no invented author and remain readable."""
    headers, _ = await _register_admin(async_client, label="historical")
    warehouse_id, source_id, _, product_id, _ = await _create_inventory_context(
        async_client, headers
    )

    async with SessionLocal() as session:
        product = await session.get(Product, uuid.UUID(product_id))
        assert product is not None
        movement = InventoryMovement(
            tenant_id=product.tenant_id,
            product_id=product.id,
            seller_id=product.seller_id,
            storage_location_id=uuid.UUID(source_id),
            warehouse_id=uuid.UUID(warehouse_id),
            quantity_delta=7,
            movement_type="historical_test",
            actor_user_id=None,
        )
        session.add(movement)
        await session.commit()
        movement_id = str(movement.id)

    listed = await async_client.get(
        "/operations/inventory-movements", headers=headers
    )
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json() if item["id"] == movement_id)
    assert row["actor_user_id"] is None


def test_inventory_movement_actor_schema_and_additive_migration_contract() -> None:
    """Schema boundary: nullable users FK, introduced by an additive migration."""
    actor_column = InventoryMovement.__table__.c.actor_user_id
    assert actor_column.nullable is True
    assert {foreign_key.target_fullname for foreign_key in actor_column.foreign_keys} == {
        "users.id"
    }

    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    add_actor_column = re.compile(
        r'op\.add_column\(\s*"inventory_movements",\s*sa\.Column\(\s*"actor_user_id"',
        re.MULTILINE,
    )
    candidates = [
        path
        for path in versions.glob("*.py")
        if add_actor_column.search(path.read_text(encoding="utf-8"))
    ]
    assert len(candidates) == 1
    source = candidates[0].read_text(encoding="utf-8")
    upgrade = source.split("def upgrade()", maxsplit=1)[1].split(
        "def downgrade()", maxsplit=1
    )[0]
    assert "op.add_column" in upgrade
    assert "nullable=True" in upgrade
    assert 'sa.ForeignKey("users.id"' in upgrade
    assert "op.drop_column" not in upgrade
    assert "op.alter_column" not in upgrade

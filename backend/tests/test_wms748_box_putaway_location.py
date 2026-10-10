"""WMS-748: box location stays in step with stock after sorting putaway."""

from __future__ import annotations

import importlib.util
import logging
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.inbound_intake import InboundIntakeBox, InboundIntakeBoxLine
from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation
from app.services import inbound_intake_box_service as box_service
from app.services import inbound_intake_service as intake_service
from app.services.tokens import decode_access_token
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)


@pytest.mark.asyncio
async def test_sorting_putaway_updates_box_location_and_fbs_scan_picks_from_it(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    actor_id = uuid.UUID(
        str(decode_access_token(headers["Authorization"].removeprefix("Bearer "))["sub"])
    )
    seller_id, warehouse_id, cell_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"WMS748-{suffix}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=barcode, barcode=barcode
    )

    async with SessionLocal() as session:
        request = await intake_service.create_request(
            session, tenant_id, warehouse_id=warehouse_id
        )
        request_id = request.id
        line = await intake_service.add_line(
            session, tenant_id, request_id, product_id=product_id, expected_qty=1
        )
        await intake_service.patch_request_draft(
            session,
            tenant_id,
            request_id,
            planned_box_count=1,
            planned_box_count_set=True,
        )
        await intake_service.submit_request(session, tenant_id, request_id)
        await intake_service.begin_receiving(
            session, tenant_id, request_id, actor_user_id=actor_id
        )
        await intake_service.set_line_actual_qty(
            session, tenant_id, request_id, line.id, actual_qty=0
        )
        request = await intake_service.get_request(session, tenant_id, request_id)
        assert request is not None
        boxes = await box_service.create_boxes_for_request(
            session, tenant_id, request, box_count=1
        )
        box_id = boxes[0].id
        session.add(InboundIntakeBoxLine(box_id=box_id, product_id=product_id, quantity=1))
        await session.flush()
        await intake_service.sync_request_actuals_from_boxes(session, request)
        await intake_service.complete_receiving(
            session, tenant_id, request_id, actor_user_id=actor_id
        )
        box = await session.get(InboundIntakeBox, box_id)
        assert box is not None
        box_barcode = box.internal_barcode
        location = await session.get(StorageLocation, cell_id)
        assert location is not None
        location_barcode = location.barcode
        quantity_before_putaway = await session.scalar(
            sa.select(sa.func.coalesce(sa.func.sum(InventoryBalance.quantity), 0)).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.container_kind == "box",
                InventoryBalance.container_id == box_id,
            )
        )
        assert quantity_before_putaway == 1

    putaway = await async_client.post(
        f"/operations/inbound-intake-requests/{request_id}/boxes/{box_id}/putaway",
        headers=headers,
        json={"storage_location_id": str(cell_id)},
    )
    assert putaway.status_code == 200, putaway.text

    async with SessionLocal() as session:
        box = await session.get(InboundIntakeBox, box_id)
        assert box is not None
        persisted_box_location_id = box.storage_location_id
        balances = list(
            (
                await session.scalars(
                    sa.select(InventoryBalance).where(
                        InventoryBalance.tenant_id == tenant_id,
                        InventoryBalance.product_id == product_id,
                        InventoryBalance.container_kind == "box",
                        InventoryBalance.container_id == box_id,
                    )
                )
            ).all()
        )
        assert sum(balance.quantity for balance in balances) == quantity_before_putaway
        assert sum(
            balance.quantity for balance in balances if balance.storage_location_id == cell_id
        ) == quantity_before_putaway

    supply_id, order_ids, _ = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        cell_id,
        product_id,
        stock_qty=0,
        order_specs=[(748, timedelta(hours=24))],
        barcode=barcode,
    )

    selected = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/scan-location",
        headers=headers,
        json={"location_barcode": location_barcode},
    )
    assert selected.status_code == 200, selected.text
    scanned_box = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/scan",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={"barcode": box_barcode},
    )
    assert scanned_box.status_code == 200, scanned_box.text
    picked = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/scan",
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        json={
            "barcode": barcode,
            "storage_location_id": str(cell_id),
            "container_kind": "box",
            "container_id": str(box_id),
            "order_id": str(order_ids[0]),
        },
    )
    assert picked.status_code == 200, picked.text
    assert picked.json()["picked_qty"] == 1
    assert persisted_box_location_id == cell_id
    assert scanned_box.json()["storage_location_id"] == str(cell_id)


def test_data_migration_repairs_only_a_single_cell_container(
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = Path(__file__).resolve().parents[1] / (
        "alembic/versions/20261010_0723_wms748_box_location_after_putaway.py"
    )
    spec = importlib.util.spec_from_file_location("wms748_location_migration", path)
    assert spec is not None and spec.loader is not None, "WMS-748 migration must exist"
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    metadata = sa.MetaData()
    sa.Table(
        "storage_locations",
        metadata,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("warehouse_id", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("deleted_at", sa.String()),
    )
    sa.Table(
        "inbound_intake_requests",
        metadata,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("warehouse_id", sa.String(), nullable=False),
    )
    boxes = sa.Table(
        "inbound_intake_boxes",
        metadata,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("storage_location_id", sa.String()),
        sa.Column("pallet_id", sa.String()),
    )
    sa.Table(
        "inbound_intake_cargo_places",
        metadata,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("storage_location_id", sa.String()),
        sa.Column("pallet_id", sa.String()),
    )
    sa.Table(
        "warehouse_boxes",
        metadata,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("warehouse_id", sa.String(), nullable=False),
        sa.Column("container_kind", sa.String(), nullable=False),
        sa.Column("storage_location_id", sa.String()),
        sa.Column("pallet_id", sa.String()),
    )
    balances = sa.Table(
        "inventory_balances",
        metadata,
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("storage_location_id", sa.String(), nullable=False),
        sa.Column("container_kind", sa.String(), nullable=False),
        sa.Column("container_id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
    )
    engine = sa.create_engine("sqlite://")
    tenant_id, warehouse_id, request_id = "tenant", "warehouse", "request"
    sorting_id, cell_a_id, cell_b_id = "sorting", "cell-a", "cell-b"
    good_box_id, ambiguous_box_id = "good-box", "ambiguous-box"
    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(
            metadata.tables["storage_locations"].insert(),
            [
                {"id": sorting_id, "tenant_id": tenant_id, "warehouse_id": warehouse_id,
                 "code": "__SORTING__"},
                {"id": cell_a_id, "tenant_id": tenant_id, "warehouse_id": warehouse_id,
                 "code": "A-1"},
                {"id": cell_b_id, "tenant_id": tenant_id, "warehouse_id": warehouse_id,
                 "code": "A-2"},
            ],
        )
        connection.execute(
            metadata.tables["inbound_intake_requests"].insert().values(
                id=request_id, tenant_id=tenant_id, warehouse_id=warehouse_id
            )
        )
        connection.execute(
            boxes.insert(),
            [
                {"id": good_box_id, "tenant_id": tenant_id, "request_id": request_id,
                 "storage_location_id": sorting_id, "pallet_id": None},
                {"id": ambiguous_box_id, "tenant_id": tenant_id, "request_id": request_id,
                 "storage_location_id": sorting_id, "pallet_id": None},
            ],
        )
        connection.execute(
            balances.insert(),
            [
                {"id": "balance-1", "tenant_id": tenant_id, "storage_location_id": cell_a_id,
                 "container_kind": "box", "container_id": good_box_id,
                 "product_id": "product-1", "quantity": 4},
                {"id": "balance-2", "tenant_id": tenant_id, "storage_location_id": cell_a_id,
                 "container_kind": "box", "container_id": ambiguous_box_id,
                 "product_id": "product-1", "quantity": 2},
                {"id": "balance-3", "tenant_id": tenant_id, "storage_location_id": cell_b_id,
                 "container_kind": "box", "container_id": ambiguous_box_id,
                 "product_id": "product-2", "quantity": 3},
            ],
        )
        with Operations.context(MigrationContext.configure(connection)):
            monkeypatch_op = migration.op
            try:
                migration.op = Operations(MigrationContext.configure(connection))
                with caplog.at_level(logging.INFO, logger="alembic.runtime.migration"):
                    migration.upgrade()
                    migration.upgrade()
                migration.downgrade()
            finally:
                migration.op = monkeypatch_op
        updated = connection.execute(
            sa.select(boxes.c.id, boxes.c.storage_location_id).order_by(boxes.c.id)
        ).all()
        assert dict(updated) == {
            ambiguous_box_id: sorting_id,
            good_box_id: cell_a_id,
        }
        assert connection.scalar(sa.select(sa.func.sum(balances.c.quantity))) == 9
    assert "ambiguous=1" in caplog.text
